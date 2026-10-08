# Override for PyInstaller's stock gi.repository.Gtk hook.
#
# The stock hook bundles ALL of /usr/share/{icons,themes} by default
# (~1 GB uncompressed: every cursor/icon theme on the build machine).
# The frozen app uses the host system's GTK data at runtime, so typelib
# data alone is enough — collect nothing else.
from PyInstaller.utils.hooks.gi import GiModuleInfo


def hook(hook_api):
    module_info = GiModuleInfo("Gtk", "3.0", hook_api=hook_api)
    if not module_info.available:
        return
    binaries, datas, hiddenimports = module_info.collect_typelib_data()
    hook_api.add_datas(datas)
    hook_api.add_binaries(binaries)
    hook_api.add_imports(*hiddenimports)
