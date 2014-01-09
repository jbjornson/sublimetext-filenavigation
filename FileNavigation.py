import sublime, sublime_plugin
import glob, os

class FileNavigationHelper(object):
    _instance = None

    @classmethod
    def instance(cls):
        """Basic singleton implementation"""
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.sublime_settings = sublime.load_settings('Preferences.sublime-settings')
        self.excluded_extensions = self.sublime_settings.get('binary_file_patterns') + self.sublime_settings.get('file_exclude_patterns')
        self.reset()

    def track_calling_view(self, window):
        self.calling_view = window.active_view()
        self.calling_view_index = window.get_view_index(self.calling_view)
        self.calling_view_is_empty = len(window.views()) == 0

        return self.calling_view.file_name()

    def get_current_view_index(self):
        if self.calling_view_is_empty:
            return (0, -1)
        else:
            return self.calling_view_index

    def set_preview(self, file_path):
        self.preview_file_path = file_path
        self.set_plugin_visibility(True)

    def set_plugin_visibility(self, is_active):
        # Use a special setting so we can isolate the context for the quick-open command's keymap entry
        if is_active:
            self.sublime_settings.set('file_navigation_active', True)
        else:
            self.sublime_settings.erase('file_navigation_active')

    def get_preview_path(self):
        return self.preview_file_path

    def reset(self):
        self.preview_file_path = None

        self.calling_view = None
        self.calling_view_is_empty = None

        self.set_plugin_visibility(False)

    def show_calling_view(self, window):
        if self.calling_view_is_empty:
            window.run_command("close_file")
        else:
            window.focus_view( self.calling_view )

    def get_dir_from_path(self, current_file):
        path = os.path.dirname(current_file) if os.path.isfile(current_file) else current_file
        return os.path.normpath(path)

    def get_listing(self, current_file):
        stack = {}
        # Iterate over the list of files and add them to the display list
        path = self.get_dir_from_path(current_file)
        dir_listing = glob.glob(os.path.join(path, '*'))

        # Filter out the binary and ignored file extensions
        for file_path in dir_listing:
            extension = '*' + os.path.splitext(file_path)[1].lower()
            if extension in self.excluded_extensions:
                dir_listing.remove(file_path)

        # Build up the file list for display
        stack[current_file] = []

        # Add the parent directory
        parent = os.path.abspath(os.path.join(path, os.pardir))
        if not os.path.samefile(path, parent):
            stack[current_file].append([os.pardir, parent])

        # Add all the files in this directory (aside from the current)
        for (index, file_path) in enumerate(dir_listing):
            if self.skip_file(file_path):
                continue

            if self.is_same_file(file_path, current_file):
                continue

            # If this is a sub-folder, then add a slash at the end
            label = os.path.basename(file_path)
            if os.path.isdir(file_path):
                label += '/'
            stack[current_file].append([label, self.get_dir_from_path(file_path)])

        return stack


    def is_same_file(self, file_path, other_file_path):
        samefile = False
        try:
            if os.path.samefile(file_path, other_file_path):
                samefile = True
        except OSError:
            samefile = False
        return samefile


    # os.access blatantly lies and os.stat throws an exception rather than telling me I have no permission
    # Apparently is is easier to catch failed access rather than check the permissions (especially on windows)
    def skip_file(self, file_path):
        skip = False
        try:
            if os.path.exists(file_path):
                skip = False
        except OSError:
            skip = True
        return skip


class QuickOpenFileNavigationCommand(sublime_plugin.WindowCommand):
    def run(self):
        file_path = FileNavigationHelper.instance().get_preview_path()

        # Only try to open if this is actually a file
        if not file_path or not os.path.isfile(file_path):
            return

        # Only try to open and position the file if it is still transient
        view = self.window.find_open_file(file_path)
        if view == self.window.transient_view_in_group(self.window.active_group()) or not view:
            (group, index) = FileNavigationHelper.instance().get_current_view_index()
            view = self.window.open_file(file_path)
            self.window.set_view_index(view, group, index + 1)

class FileNavigationCommand(sublime_plugin.WindowCommand):
    def run(self):
        current_file = FileNavigationHelper.instance().track_calling_view(self.window)
        if not current_file:
            current_file = os.getcwd()

        self.stack = {}
        self.navigate(current_file)


    def navigate(self, path_to_navigate):
        self.stack = FileNavigationHelper.instance().get_listing(path_to_navigate)

        on_done = lambda i, cwd=path_to_navigate: self.open_selected_file(cwd, i)
        on_selected = lambda i, cwd=path_to_navigate: self.show_preview(cwd, i)

        self.window.show_quick_panel(self.stack[path_to_navigate], on_done, selected_index=0, on_highlight=on_selected)

    def open_selected_file(self, path, selected_index):
        if selected_index < 0:
            # The user cancelled the action - give the focus back to the "calling" view
            FileNavigationHelper.instance().show_calling_view(self.window)
            FileNavigationHelper.instance().reset()
        else:
            file_path = self.get_path(self.stack[path][selected_index])

            # If the selected item is a file then open it, otherwise recursively navigate the selected directory
            if os.path.isfile(file_path):
                # Open the selected file
                self.window.open_file(file_path)
                FileNavigationHelper.instance().reset()
            else:
                FileNavigationHelper.instance().show_calling_view(self.window)
                # Navigate the selected directory
                sublime.set_timeout_async(lambda s=file_path: self.navigate(s), 0)

    def show_preview(self, path, selected_index):
        if selected_index >= 0:
            file_path = self.get_path(self.stack[path][selected_index])

            FileNavigationHelper.instance().set_preview(file_path)

            if os.path.isfile(file_path):
                self.window.open_file(file_path, sublime.TRANSIENT)
            else:
                FileNavigationHelper.instance().show_calling_view(self.window)

    def get_path(self, stack_entry):
        name = stack_entry[0]
        directory = stack_entry[1]
        if name == os.pardir or name.endswith('/'):
            file_path = directory
        else:
            file_path = os.path.join(directory, name)
        return file_path
