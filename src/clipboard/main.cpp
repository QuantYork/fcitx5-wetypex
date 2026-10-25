#include <QBuffer>
#include <QClipboard>
#include <QFile>
#include <QGuiApplication>
#include <QImage>
#include <QTimer>
#include <cstdio>
#include <csignal>
#include <cstring>
#include <sys/prctl.h>
#include <unistd.h>
#include <wayland-client.h>

static int clipboardProtocols() {
  auto *display = wl_display_connect(nullptr);
  if (!display)
    return 2;
  struct Protocols {
    bool wlr = false;
    bool ext = false;
  } protocols;
  auto *registry = wl_display_get_registry(display);
  static const wl_registry_listener listener{
      [](void *data, wl_registry *, uint32_t, const char *name, uint32_t) {
        auto &protocols = *static_cast<Protocols *>(data);
        if (std::strcmp(name, "zwlr_data_control_manager_v1") == 0)
          protocols.wlr = true;
        if (std::strcmp(name, "ext_data_control_manager_v1") == 0)
          protocols.ext = true;
      },
      [](void *, wl_registry *, uint32_t) {}};
  wl_registry_add_listener(registry, &listener, &protocols);
  const bool ready = wl_display_roundtrip(display) >= 0;
  wl_registry_destroy(registry);
  wl_display_disconnect(display);
  if (!ready)
    return 2;
  if (protocols.wlr)
    std::puts("zwlr_data_control_manager_v1");
  if (protocols.ext)
    std::puts("ext_data_control_manager_v1");
  return 0;
}

int main(int argc, char **argv) {
  // Query only the registry, before Qt can initialize a clipboard or surface.
  if (argc == 2 && std::strcmp(argv[1], "--wayland-clipboard-protocols") == 0)
    return clipboardProtocols();
  QGuiApplication app(argc, argv);
  const QStringList arguments = app.arguments();
  if (arguments.contains("--read-text")) {
    int result = 1;
    QTimer::singleShot(100, &app, [&] {
      const QByteArray text = QGuiApplication::clipboard()->text().toUtf8();
      QFile output;
      if (!text.isEmpty() && text.size() <= 65536 &&
          output.open(stdout, QIODevice::WriteOnly) &&
          output.write(text) == text.size())
        result = 0;
      else if (text.size() > 65536)
        result = 2;
      app.exit();
    });
    app.exec();
    return result;
  }
  if (arguments.contains("--read-image")) {
    int result = 1;
    QTimer::singleShot(100, &app, [&] {
      const QImage image = QGuiApplication::clipboard()->image();
      if (!image.isNull()) {
        QByteArray png;
        QBuffer buffer(&png);
        buffer.open(QIODevice::WriteOnly);
        QFile output;
        if (image.save(&buffer, "PNG") && png.size() <= 8388608 &&
            output.open(stdout, QIODevice::WriteOnly) &&
            output.write(png) == png.size())
          result = 0;
        else
          result = 2;
      }
      app.exit();
    });
    app.exec();
    return result;
  }
  QFile input;
  if (!input.open(stdin, QIODevice::ReadOnly))
    return 2;
  QByteArray bytes =
      input.read(arguments.contains("--image")             ? 8388609
                 : arguments.contains("--normalize-image") ? 8388609
                                                           : 65537);
  if (bytes.isEmpty() ||
      bytes.size() > (arguments.contains("--image") ||
                              arguments.contains("--normalize-image")
                          ? 8388608
                          : 65536))
    return 2;
  if (arguments.contains("--normalize-image")) {
    const QImage image = QImage::fromData(bytes);
    QBuffer output;
    output.open(QIODevice::WriteOnly);
    if (image.isNull() || !image.save(&output, "PNG") ||
        output.data().size() > 8388608)
      return 2;
    QFile stream;
    if (!stream.open(stdout, QIODevice::WriteOnly) ||
        stream.write(output.data()) != output.data().size())
      return 2;
    return 0;
  }
  if (arguments.contains("--image")) {
    const QImage image = QImage::fromData(bytes);
    if (image.isNull())
      return 2;
    QGuiApplication::clipboard()->setImage(image, QClipboard::Clipboard);
  } else {
    auto text = QString::fromUtf8(bytes);
    QGuiApplication::clipboard()->setText(text, QClipboard::Clipboard);
  }
  // X11 selections are owned by a client. Keep this tiny process alive long
  // enough for a clipboard manager or the target application to request it.
  if (arguments.contains("--notify-ready")) {
    // A managed owner outlives the old one-minute CLI timeout, but stops
    // when its daemon exits or another application replaces the selection.
    const pid_t parent = getppid();
    if (parent == 1 || prctl(PR_SET_PDEATHSIG, SIGTERM) < 0 ||
        getppid() != parent)
      return 2;
    QObject::connect(QGuiApplication::clipboard(), &QClipboard::changed, &app,
                     [&app](QClipboard::Mode mode) {
                       if (mode == QClipboard::Clipboard &&
                           !QGuiApplication::clipboard()->ownsClipboard())
                         app.quit();
                     });
    std::puts("ready");
    std::fflush(stdout);
  } else
    QTimer::singleShot(60000, &app, &QCoreApplication::quit);
  return app.exec();
}
