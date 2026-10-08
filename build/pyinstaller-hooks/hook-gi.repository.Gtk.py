# PyInstaller hook for gi.repository.Gtk (extends the stock hook).
#
# Additionally collects the WebKit2 typelib data — no stock hook covers
# it, and the chat window needs it. Provider libs come along, minus the
# dlopen-only media/codec tail (libavcodec, x265, ...): those arrive via
# the gstreamer provider closure but only implement audio/video
# playback, which a chat window never uses. gstreamer's CORE libs stay —
# libwebkit2gtk links them directly (see ldd).
#
# NOTE: bulk theme/icon/plugin trimming is NOT done here — that comes
# from the spec's hooksconfig (gi.icons/themes, gstreamer.include_plugins),
# because additional-hooks-dir hooks CHAIN with stock hooks instead of
# replacing them.
import os
import re

from PyInstaller.utils.hooks.gi import GiModuleInfo

_DROP_BINARIES = re.compile(
    r"lib(avcodec|avformat|avfilter|avutil|avdevice|postproc|swscale|"
    r"swresample|x264|x265|placebo|lapack|blas|svt[a-z0-9]*|codec2|"
    r"dav1d|aom|vpx|mp3lame|theora|vorbis|opus|speex|webp|openjp2|"
    r"jxl|avif|openh264|xvidcore|zvbi|rabbitmq|gstlibav|fluidsynth|"
    r"chromaprint|dvdnav|dvdread|bluray|ass|srt|mfx|va|vpl)"
)


def _keep_binary(dest):
    return not _DROP_BINARIES.match(os.path.basename(dest).lower())


def hook(hook_api):
    binaries, datas, hiddenimports = [], [], []
    # (Gtk, 3.0) entry: stock hook also runs (chained); with the spec's
    # hooksconfig it contributes only typelib data, same as here.
    for namespace, version in (("Gtk", "3.0"), ("WebKit2", "4.1")):
        module_info = GiModuleInfo(namespace, version, hook_api=hook_api)
        if not module_info.available:
            continue
        b, d, h = module_info.collect_typelib_data()
        binaries += [x for x in b if _keep_binary(x[0])]
        datas += d
        hiddenimports += h
    hook_api.add_datas(datas)
    hook_api.add_binaries(binaries)
    hook_api.add_imports(*hiddenimports)
