"""Clipboard routing tests; no daemon, real display, account or clipboard access."""
import ast
import io
from pathlib import Path
import types
import unittest
from unittest.mock import Mock


def load_functions():
    source = (Path(__file__).resolve().parents[1] /
              'scripts/fcitx5-wetypex-syncd.sh.in').read_text()
    tree = ast.parse(source)
    # The script starts a persistent daemon at module scope. Load imports and
    # definitions only, so these tests cannot touch user state or start it.
    definitions = [node for node in tree.body
                   if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))]
    namespace = {}
    exec(compile(ast.Module(body=definitions, type_ignores=[]),
                 '<syncd-functions>', 'exec'), namespace)
    namespace.update(wl_paste='wl-paste', wl_copy='wl-copy',
                     clipboard_helper='clipboard-helper', clipboard_owner=None,
                     _needs_visible_surface=None,
                     _x11_environment_cache=None, _x11_environment_probed=False)
    return namespace


class ClipboardFocusTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_functions()
        self.env = {'XDG_CURRENT_DESKTOP': 'KDE', 'DISPLAY': ':1'}

    def test_known_desktops_do_not_probe_with_wl_paste(self):
        probe = Mock(side_effect=AssertionError('visible probe'))
        self.ns['_compositor_needs_visible_surface'] = probe
        for desktop in ('KDE', 'kde', 'ubuntu:KDE', 'GNOME', 'ubuntu:GNOME'):
            with self.subTest(desktop=desktop):
                self.assertTrue(self.ns['_detect_visible_surface'](
                    {'XDG_CURRENT_DESKTOP': desktop}))
        probe.assert_not_called()

    def test_other_desktops_still_probe(self):
        probe = self.ns['_compositor_needs_visible_surface'] = Mock(return_value=False)
        self.assertFalse(self.ns['_detect_visible_surface'](
            {'XDG_CURRENT_DESKTOP': 'sway'}))
        probe.assert_called_once()

    def test_silent_read_success(self):
        self.ns['surface_required'] = Mock(return_value=True)
        item = ('text', b'synthetic', 'digest')
        self.ns['_local_clipboard_silently'] = Mock(return_value=item)
        self.ns['clipboard_command'] = Mock(side_effect=AssertionError('visible read'))
        self.assertEqual(self.ns['local_clipboard'](self.env), item)
        self.ns['clipboard_command'].assert_not_called()

    def test_failed_silent_read_never_falls_back(self):
        self.ns['surface_required'] = Mock(return_value=True)
        self.ns['_local_clipboard_silently'] = Mock(return_value=None)
        self.ns['clipboard_command'] = Mock(side_effect=AssertionError('visible fallback'))
        self.assertIsNone(self.ns['local_clipboard'](self.env))
        self.ns['clipboard_command'].assert_not_called()

    def test_native_read_route_still_works(self):
        self.ns['surface_required'] = Mock(return_value=False)
        command = self.ns['clipboard_command'] = Mock(side_effect=[
            types.SimpleNamespace(returncode=0, stdout=b'text/plain\n'),
            types.SimpleNamespace(returncode=0, stdout=b'synthetic')])
        item = self.ns['local_clipboard'](self.env)
        self.assertEqual(item[:2], ('text', b'synthetic'))
        self.assertEqual(command.call_args_list[0].args[0], ['wl-paste', '--list-types'])

    def test_remote_write_without_silent_display_is_skipped(self):
        self.ns['surface_required'] = Mock(return_value=True)
        self.ns['_x11_environment'] = Mock(return_value=None)
        process = self.ns['subprocess'] = types.SimpleNamespace(
            run=Mock(side_effect=AssertionError('visible copy')),
            Popen=Mock(side_effect=AssertionError('visible helper')))
        self.assertFalse(self.ns['set_remote_clipboard']('text', b'synthetic', self.env))
        process.run.assert_not_called()
        process.Popen.assert_not_called()

    def test_remote_silent_write_uses_xcb_helper(self):
        for kind in ('text', 'image'):
            with self.subTest(kind=kind):
                ns = load_functions()
                ns['surface_required'] = Mock(return_value=True)
                xcb = dict(self.env, QT_QPA_PLATFORM='xcb')
                ns['_x11_environment'] = Mock(return_value=xcb)
                owner = types.SimpleNamespace(stdout=io.BytesIO(b'ready\n'))
                popen = Mock(return_value=owner)
                ns['subprocess'] = types.SimpleNamespace(
                    Popen=popen, PIPE=-1, DEVNULL=-3,
                    run=Mock(side_effect=AssertionError('visible wl-copy')))
                ns['select'] = types.SimpleNamespace(select=lambda *args: ([owner.stdout], [], []))
                ns['stop_clipboard_owner'] = Mock()
                self.assertTrue(ns['set_remote_clipboard'](kind, b'synthetic', self.env))
                self.assertEqual(popen.call_args.kwargs['env']['QT_QPA_PLATFORM'], 'xcb')
                self.assertEqual(popen.call_args.args[0][0], 'clipboard-helper')
                self.assertEqual('--image' in popen.call_args.args[0], kind == 'image')
                self.assertIs(ns['clipboard_owner'], owner)
                ns['subprocess'].run.assert_not_called()

    def test_native_remote_write_still_uses_wl_copy(self):
        self.ns['surface_required'] = Mock(return_value=False)
        run = Mock(return_value=types.SimpleNamespace(returncode=0))
        self.ns['subprocess'] = types.SimpleNamespace(run=run, DEVNULL=-3)
        self.ns['stop_clipboard_owner'] = Mock()
        self.assertTrue(self.ns['set_remote_clipboard']('text', b'synthetic', self.env))
        self.assertEqual(run.call_args.args[0][0], 'wl-copy')


if __name__ == '__main__':
    unittest.main()
