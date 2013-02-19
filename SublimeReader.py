import sublime
import sublime_plugin
import threading
import webbrowser
from libgreader import GoogleReader, ClientAuthMethod
from HTMLParser import HTMLParser
from datetime import datetime


class HTMLStripper(HTMLParser):
    def __init__(self):
        self.reset()
        self.fed = []
    def handle_data(self, d):
        self.fed.append(d)
    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = HTMLStripper()
    s.feed(html)
    return s.get_data()


class SublimeReaderCommand(sublime_plugin.WindowCommand):
    def __init__(self, *args, **kwargs):
        super(SublimeReaderCommand, self).__init__(*args, **kwargs)
        self.initalized = False
        self.settings = sublime.load_settings("SublimeReader.sublime-settings")
        self.timestamp = None
        self.login = self.settings.get('sublime_reader_login', 'replace with your email')
        self.password = self.settings.get('sublime_reader_password', 'replace with your password')
        
        if self.login == 'replace with your email':
            self.window.show_input_panel("Google Reader Email:", "", self.set_email, None, None)

        if self.login != 'replace with your email' and self.password == 'replace with your password':
            self.window.show_input_panel("Google Reader Password:", "", self.set_password, None, None)
        self.buffered = False
        self.items = []
        if self.login != 'replace with your email' and self.password != 'replace with your password':
            thread = InitThread(self)
            thread.start()

    def set_email(self, text):
        self.settings.set('sublime_reader_login', text)
        self.login = text
        sublime.save_settings('SublimeReader.sublime-settings')
        if self.password == 'replace with your password':
            self.window.show_input_panel("Google Reader Password:", "", self.set_password, None, None)

    def set_password(self, text):
        self.settings.set('sublime_reader_password', text)
        self.password = text
        sublime.save_settings('SublimeReader.sublime-settings')
        thread = InitThread(self)
        thread.start()

    def run(self, will_display=True, pre_save=False):
        if not self.initalized:
            sublime.set_timeout(lambda: self.run(will_display), 1000)
            return False

        self.view = self.window.active_view()
        self.will_display = will_display
        threads = []
        if pre_save:
            self.buffered = False
        current_time = datetime.now()

        if self.timestamp and (current_time - self.timestamp) < self.settings.get('sr_delay', 300):
            self.buffered = true
        else:
            self.timestamp = current_time        

        if not self.buffered:
            thread = LoadThread(self)
            threads.append(thread)
            thread.start()
        self.handle_threads(threads)

    def handle_threads(self, threads, i=0, dir=1):
        next_threads = []
        for thread in threads:
            if thread.is_alive():
                next_threads.append(thread)
                continue
        threads = next_threads
        if len(threads):
            # This animates a little activity indicator in the status area
            before = i % 8
            after = (7) - before
            if not after:
                dir = -1
            if not before:
                dir = 1
            i += dir
            self.view.set_status('gread', 'Fetching news... [%s=%s]' % \
                (' ' * before, ' ' * after))

            sublime.set_timeout(lambda: self.handle_threads(threads,
                i, dir), 250)
            return

        self.view.erase_status('gread')
        sublime.status_message('%s unread items' % (len(self.items)))
        if self.settings.get('show_content', True):
            self.trim_content()

        if self.will_display:
            if self.settings.get('always_check_for_new_items', False) or len(self.items) == 0:
                self.buffered = False
            if len(self.items) > 0:
                self.window.show_quick_panel(self.list_items(), self.displayItem)

    def displayItem(self, param):
        if param == len(self.items):
            self.buffered = False
            thread = MarkAllRead(self)
            thread.start()
        elif param > -1:
            if self.settings.get('load_in_browser', True):
                webbrowser.open_new_tab(self.items[param].url)
            else:
                new_file = self.window.new_file()
                edit = new_file.begin_edit()
                new_file.insert(edit, 0, self.items[param].content)
                new_file.end_edit(edit)
            self.items.pop(param).markRead()

    def list_items(self):
        result = []
        for item in self.items:
            string = item.title
            if self.settings.get('show_content', True):
                string = [string, item.content]
            result.append(string)

        result.append('Mark all read')
        return result

    def trim_content(self):
        for item in self.items:
            item.content = strip_tags(item.content)[:160]

    def update_items(self):
        self.items = []
        for feed in self.FEEDS:
            feed.loadItems(excludeRead=True)
            self.items += feed.getItems()
        return True


class LoadThread(threading.Thread):
    def __init__(self, plugin):
        self.plugin = plugin
        threading.Thread.__init__(self)

    def run(self):
        self.plugin.update_items()
        self.plugin.buffered = True
        return True


class MarkAllRead(threading.Thread):
    def __init__(self, plugin):
        self.plugin = plugin
        threading.Thread.__init__(self)

    def run(self):
        for feed in self.plugin.FEEDS:
            self.plugin.reader.markFeedAsRead(feed)


class InitThread(threading.Thread):
    """
    Initlize GoogleReader in a new thread.
    """
    def __init__(self, plugin):
        self.plugin = plugin
        threading.Thread.__init__(self)

    def run(self):
        auth = ClientAuthMethod(self.plugin.login, self.plugin.password)        
        self.plugin.reader = GoogleReader(auth)
        self.plugin.reader.buildSubscriptionList()
        self.plugin.FEEDS = self.plugin.reader.getFeeds()
        self.plugin.initalized = True


class ReadOnSave(sublime_plugin.EventListener):
    """
    Runs the main plugin before the file is saved.
    """
    def on_pre_save(self, view):
        s = sublime.load_settings('SublimeReader.sublime-settings')
        will_display = s.get('load_on_save', False)
        view.window().run_command('sublime_reader', {"will_display": will_display, "pre_save": True})
