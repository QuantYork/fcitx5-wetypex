"""Integration checks for a compiled plugin, with a synthetic backend.

Run with dbus-run-session. Requires python3-dbus and python3-gi.
No real user state, input core, display or clipboard is used.
"""
import os,subprocess,tempfile,pathlib,time,json,dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
DBusGMainLoop(set_as_default=True)
bus=dbus.SessionBus();root=pathlib.Path(__file__).resolve().parents[1]
if bus.name_has_owner('org.fcitx.Fcitx5'):
 raise SystemExit('Use dbus-run-session: refusing to touch an existing Fcitx5 session')
addon_dir=pathlib.Path(os.environ.get('PANEL_TEST_ADDON_DIR',str(root/'build'))).resolve()
if not (addon_dir/'wetypex.so').is_file():
 raise SystemExit('Build wetypex.so first or set PANEL_TEST_ADDON_DIR')

def pump(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
  time.sleep(.001)

def run_case(name,delay,no_candidates=False,focus_out=False):
 with tempfile.TemporaryDirectory(prefix='wetypex-panel-test-') as temp:
  home=pathlib.Path(temp);conf=home/'.config/fcitx5';conf.mkdir(parents=True)
  (conf/'profile').write_text('[Groups/0]\nName=Test\nDefault Layout=us\nDefaultIM=wetypex\n\n[Groups/0/Items/0]\nName=keyboard-us\n\n[Groups/0/Items/1]\nName=wetypex\n\n[GroupOrder]\n0=Test\n')
  (conf/'wetypex.json').write_text(json.dumps({'standalone':True,'preedit_position':'candidate','ai_assistant':False,'v_mode':False}))
  env=dict(os.environ,HOME=temp,XDG_CONFIG_HOME=str(home/'.config'),XDG_DATA_HOME=str(home/'.local/share'),FCITX_CONFIG_HOME=str(conf),FCITX_ADDON_DIRS=str(addon_dir)+':'+os.environ.get('PANEL_TEST_SYSTEM_ADDON_DIR','/usr/lib/x86_64-linux-gnu/fcitx5'),WETYPE_BACKEND_LAUNCHER=str(root/'tests/fixtures/initial-panel-backend.py'),WETYPE_SYNCD_LAUNCHER='/bin/true',PANEL_TEST_DELAY=str(delay))
  for key in ['DISPLAY','WAYLAND_DISPLAY','WAYLAND_SOCKET','FCITX_CONFIG_DIRS']:env.pop(key,None)
  if no_candidates:env['PANEL_TEST_NO_CANDIDATES']='1'
  log_path=home/'fcitx.log';log=open(log_path,'w')
  process=subprocess.Popen(['fcitx5','--keep','--disable=all','--enable=keyboard,wetypex,dbus,dbusfrontend,classicui,clipboard'],env=env,stdout=log,stderr=log)
  try:
   end=time.monotonic()+5
   while not bus.name_has_owner('org.fcitx.Fcitx5'):
    if process.poll() is not None:raise RuntimeError(log_path.read_text()[-3000:])
    if time.monotonic()>end:raise RuntimeError('D-Bus startup timed out')
    pump(.02)
   pump(.1)
   portal=dbus.Interface(bus.get_object('org.fcitx.Fcitx5','/org/freedesktop/portal/inputmethod'),'org.fcitx.Fcitx.InputMethod1')
   path,_=portal.CreateInputContext([('program','panel-regression'),('display',':99')])
   ic=dbus.Interface(bus.get_object('org.fcitx.Fcitx5',path),'org.fcitx.Fcitx.InputContext1')
   ctl=dbus.Interface(bus.get_object('org.fcitx.Fcitx5','/controller'),'org.fcitx.Fcitx.Controller1')
   events=[];start=[time.monotonic()]
   def update(*args):
    preedit=''.join(str(v[0]) for v in args[0]); candidates=[str(v[1]) for v in args[4]]
    if preedit or candidates:events.append((time.monotonic()-start[0],preedit,candidates))
   handle=bus.add_signal_receiver(update,signal_name='UpdateClientSideUI',dbus_interface='org.fcitx.Fcitx.InputContext1',path=path)
   ic.SetCapability(dbus.UInt64((1<<39)|2|16));ic.FocusIn();ctl.SetCurrentIM('wetypex');ctl.Activate();pump(.1)
   events.clear();start[0]=time.monotonic();assert ic.ProcessKeyEvent(ord('n'),0,0,False,0)
   if focus_out:pump(.01);ic.FocusOut()
   pump(.5)
   if focus_out:assert not events,events
   elif delay<.1 and not no_candidates:assert events and events[0][2],events
   elif no_candidates:assert events and events[0][1] and .015<events[0][0]<.1,events
   else:assert events and not events[0][2] and .075<events[0][0]<.2 and any(e[2] for e in events),events
   print('PASS',name,[(round(t,3),bool(p),bool(c)) for t,p,c in events[:3]],flush=True)
   handle.remove();ic.DestroyIC()
  finally:
   process.terminate()
   try:process.wait(timeout=4)
   except subprocess.TimeoutExpired:process.kill();process.wait()
   log.close();pump(.05)
for case in [('fast-candidates',.03,False,False),('bounded-fallback',.3,False,False),('no-candidates',.03,True,False),('focus-cancellation',.3,False,True)]:run_case(*case)
