"""Copyright (C) 2017  The University of Manchester

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import json
import logging
import errno
import gi
import re
from collections import namedtuple
from datetime import timedelta, datetime, tzinfo
from requests_futures.sessions import FuturesSession

gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango
from galicaster.core import context
from galicaster.classui import get_ui_path
from galicaster.classui import get_image_path
from galicaster.classui.elements.message_header import Header
from galicaster.mediapackage import mediapackage
from galicaster.utils.i18n import _

# This is the name of this plugin's section in the configuration file
CONFIG_SECTION = "set_user"

# REGEXP Defaults and Keys
DEFAULT_REGEXP_LECTURER = "[0-9]{8}"
DEFAULT_REGEXP_LEARNER = "[a-zA-z]{6}[0-9]{3}"
REGEXP_LECTURER = "rexexp_lecturer"
REGEXP_LEARNER = "rexexp_learner"

# URL to request user information from
DEFAULT_URL = "http://camonitor.uct.ac.za/obs-api/event/owner/"
DEFAULT_CREATE_URL = "http://camonitor.uct.ac.za/obs-api/series/"
URL_GET = "get"
URL_POST = "create"

timeout_id = None

def init():
    global recorder, dispatcher, logger, config, repo

    config = context.get_conf().get_section(CONFIG_SECTION) or {}
    dispatcher = context.get_dispatcher()
    repo = context.get_repository()
    logger = context.get_logger()
    recorder = context.get_recorder()

    try:
        dispatcher.connect("init", init_user_ui)

    except Exception as e:
        logger.error(e)
    logger.info("Set user loaded.")

def init_user_ui(element):
    """
    Add the UI elements to set the user info
    :param element:
    :return:
    """
    global recorder_ui, res, logger

    # load glade file
    #builder = Gtk.Builder()
    #builder.add_from_file(get_ui_path("camctrl-vapix.glade"))

    # calculate resolution for scaling
    #window_size = context.get_mainwindow().get_size()
    #res = window_size[0]/1920.0

    recorder_ui = context.get_mainwindow().nbox.get_nth_page(0)

    controller = UserController(logger, recorder_ui)
    #dispatcher.connect("recorder-starting", controller.on_start_recording)
    #dispatcher.connect("recorder-stopped", controller.on_stop_recording)

    logger.info("Set user init done.")

class UserController():
    """
    Handle the buttons on the main ui
    """
    def __init__(self, _logger, _ui):
        self.__logger = _logger
        self.__ui = _ui

        self.details = None

        # so overwrite the default record button function
        rec_button = self.__ui.gui.get_object("recbutton")
        rec_button.connect("clicked", self.on_rec)
        rec_button.handler_block_by_func(self.__ui.on_rec)

        # add new settings tab to the notebook
        self.box = self.__ui.gui.get_object("eventpanel") #hbox4")
        self.title = self.__ui.gui.get_object("titlelabel")
        #status = self.__ui.get_object("eventlabel")

        new_box = Gtk.Box(spacing=0)
        new_box.set_name("set_user_container")

        label = Gtk.Label("")
        new_box.pack_start(label, expand=False, fill=False, padding=30)

        self.btn_show = Gtk.Button("Select a user...")
        self.btn_show.set_name("set_user_btn_set")
        self.btn_show.connect("clicked", self.button_set_user)
        new_box.pack_start(self.btn_show, expand=True, fill=True, padding=10)

        img_clear = Gtk.Image()
        img_clear.set_from_icon_name("edit-clear-symbolic", 6)

        self.btn_clear = Gtk.Button()
        self.btn_clear.set_name("set_user_btn_clear")
        #button.set_label("gtk-clear")
        self.btn_clear.connect("clicked", self.button_clear_user)
        self.btn_clear.add(img_clear)
        self.btn_clear.set_sensitive(False) # disabled
        new_box.pack_start(self.btn_clear, expand=True, fill=True, padding=10)

        label = Gtk.Label("")
        new_box.pack_start(label, expand=False, fill=True, padding=30)

        self.box.pack_start(new_box, False, False, 10)
        self.box.show_all()

    def button_set_user(self, button):
        self.__logger.info("SET USER")
        popup = SetUserClass(self.__logger, title="Get My Info")

        if popup.return_value == -10:
            self.btn_clear.set_sensitive(True) # enabled
            self.details = {
                                'series': popup.series_id,
                                'seriesTitle': popup.series_title,
                                'organizer': popup.user_name,
                                'organizerEmail': popup.user_email,
                                'take': 0
                            }
            self.btn_show.set_label(popup.user_name +" [Change]")
            self.title.set_text("Live with " + self.details['organizer'])
            self.box.show_all()
            self.__logger.info("User details set to: "+ popup.id +" "+ popup.user_name)

        if popup.return_value == -7:
            self.__logger.info("Cancelled")

    def button_clear_user(self, button):
        self.__logger.info("CLEAR USER")
        self.details = None
        self.btn_clear.set_sensitive(False) # disabled
        self.btn_show.set_label("Select a user...")
        self.title.set_text(_("No upcoming events"))
        self.box.show_all()

    def on_rec(self, elem):
        recorder.record(self.create_mp())
        self.__logger.info("# Start Recording")

    def create_mp(self):
        if self.details is None:
            return None

        self.details['take'] += 1
        title = self.details['organizer'].strip() + ' - Take #' + str(self.details['take'])
        new_mp = mediapackage.Mediapackage(title=title)
        new_mp.setSeries({
            'title': self.details['seriesTitle'],
            'identifier': self.details['series']
        })
        return new_mp

class SetUserClass(Gtk.Widget):
    """
    Handle a pop up to select a user
    """
    __gtype_name__ = 'SetUserClass'

    def __init__(self, _logger=None, title="Get My Info"):
        """
        """
        self.id = ""
        self.user_name = ""
        self.user_email = ""
        self.series_id = ""
        self.series_title = ""

        self.__logger = _logger
        self.__url = config.get(URL_GET, DEFAULT_URL)
        self.__create_url = config.get(URL_POST, DEFAULT_CREATE_URL)
        self.__session = FuturesSession()

        regexp = config.get(REGEXP_LECTURER, DEFAULT_REGEXP_LECTURER)
        #self.__logger.info("Lecturer REGEXP = " + regexp)
        self.__lecturer = re.compile("[0-9]{8}")

        regexp = config.get(REGEXP_LEARNER, DEFAULT_REGEXP_LEARNER)
        #self.__logger.info("Learner REGEXP = " + regexp)
        self.__learner = re.compile("[a-zA-z]{6}[0-9]{3}")

        parent = context.get_mainwindow()
        size = parent.get_size()

        self.par = parent
        altura = size[1]
        anchura = size[0]
        k1 = anchura / 1920.0
        k2 = altura / 1080.0
        self.wprop = k1
        self.hprop = k2

        gui = Gtk.Builder()
        gui.add_from_file(get_ui_path('set_user.glade'))

        self.dialog = gui.get_object("setuserdialog")
        self.dialog.set_property("width-request", int(anchura/2.2))
        self.dialog.set_type_hint(Gdk.WindowTypeHint.TOOLBAR)
        self.dialog.set_modal(True)
        self.dialog.set_keep_above(False)

        #NEW HEADER
        strip = Header(size=size, title=title)
        self.dialog.vbox.pack_start(strip, True, True, 0)
        self.dialog.vbox.reorder_child(strip, 0)

        self.search_field = gui.get_object("inp_search")
        #search_field.connect('key-press-event', self.on_key_press)
        self.search_field.connect('key-release-event', self.on_key_release)
        self.search_field.connect('search-changed', self.search_changed)
        self.search_field.connect('stop-search', self.search_stopped)

        self.result = gui.get_object("grd_result")

        if parent != None:
            # FIXME: The keyboard plugin uses Ubuntu Onboard.
            # https://bugs.launchpad.net/onboard/+bug/1627819
            # There is a bug with this plugin where the "dock to edges"
            # option does not work with the "force to top" one, causing
            # Onboard to appear behind when Galicaster is on fullscreen.
            # THIS affects #321. A better solution should be implemented.
            from galicaster import plugins
            if not parent.is_fullscreen or 'galicaster.plugins.keyboard' not in plugins.loaded:
                self.dialog.set_transient_for(parent.get_toplevel())
            self.dialog.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
            dialog_style_context = self.dialog.get_style_context()
            window_classes = parent.get_style_context().list_classes()
            for style_class in window_classes:
                dialog_style_context.add_class(style_class)

        self.dialog.show_all()

        parent.get_style_context().add_class('shaded')
        self.return_value = self.dialog.run()

        parent.get_style_context().remove_class('shaded')
        self.dialog.destroy()

    def on_key_release(self, widget, ev, data=None):

        #If Escape pressed, reset text
        if ev.keyval == Gdk.KEY_Escape:
            widget.set_text("")
            self.clear_search_entry()

        #If Enter pressed, try searching
        if ev.keyval == Gdk.KEY_Return or ev.keyval == Gdk.KEY_KP_Enter:
            self.do_search(widget.get_text())

    def search_changed(self, widget, data=None):
        #self.__logger.info("search_changed")

        if widget.get_text() == "":
            self.clear_search_entry()

        if self.__lecturer.match(widget.get_text()): # if valid lecturer search
            #self.__logger.info("Lecturer :) " + widget.get_text())
            self.do_search(widget.get_text())

        if self.__learner.match(widget.get_text()): # if valid learner search
            #self.__logger.info("Learner :) " + widget.get_text())
            self.do_search(widget.get_text())

    def search_stopped(self, widget, data=None):
        #self.__logger.info("search_stopped")
        self.clear_search_entry()

    def clear_search_entry(self):
        self.search_field.set_text("")

        for element in self.result.get_children():
            self.result.remove(element)

        label = Gtk.Label("")
        self.result.pack_start(label, expand=False, fill=False, padding=0)

    def do_search(self, value):
        #self.__logger.info("Searching : " + self.__url + value)

        #if self.__lecturer.match(value): # if valid lecturer search
        #    self.__logger.info("Lecturer :) " + value)
        #else:
        #    self.__logger.info("Not Lecturer")

        #if self.__learner.match(value): # if valid learner search
        #    self.__logger.info("Learner :) " + value)
        #else:
        #    self.__logger.info("Not Learner")

        for element in self.result.get_children():
            self.result.remove(element)

        loading_box = Gtk.Box(spacing=10)
        loading_box.set_name("grd_result_loading")

        label = Gtk.Label("")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        spinner = Gtk.Spinner()
        spinner.start()
        loading_box.pack_start(spinner, expand=False, fill=False, padding=0)

        label = Gtk.Label(" Searching... ")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        label = Gtk.Label("")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        self.result.pack_start(loading_box, expand=False, fill=False, padding=0)
        self.result.show_all()

        future = self.__session.get(self.__url + value, background_callback=self.show_response)
        #response = future.result()
        #self.__logger.info('response status {0}'.format(response.status_code))

    def show_response(self, sess, resp):
        self.__logger.info("request returned.")

        for element in self.result.get_children():
            self.result.remove(element)

        if resp.ok:
            details = json.loads(resp.content, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))

            if details.fullname:
                self.id = details.username
                self.user_name = details.fullname
                self.user_email = details.email

                result_box = Gtk.Box(spacing=30)
                result_box.set_name("grd_result_button")

                button = Gtk.Button()
                button.set_name("btn_select_user")
                button.set_relief(Gtk.ReliefStyle.NONE)
                button_box = Gtk.Box(spacing=10)
                button.add(button_box)

                #self.__logger.info("Found: " + details.fullname)
                label = Gtk.Label(details.fullname)

                img_series = Gtk.Image()

                if details.ocSeries:
                    img_series.set_from_icon_name("object-select-symbolic", 2)
                    #self.__logger.info("     Series: " + details.ocSeries[0].identifier)
                    button.connect("clicked", self.close_modal)
                    self.series_id = details.ocSeries[0].identifier
                    self.series_title = details.ocSeries[0].title
                else:
                    img_series.set_from_icon_name("star-new-symbolic", 2)
                    button.connect("clicked", self.create_series)
                    self.series_id = ""
                    self.series_title = ""

                button_box.pack_start(img_series, expand=False, fill=False, padding=10)
                button_box.pack_start(label, expand=False, fill=False, padding=10)

                label = Gtk.Label("select")
                label.set_markup('<span foreground="#494941" face="sans" size="small">select</span>')
                button_box.pack_start(label, expand=False, fill=False, padding=10)

                result_box.pack_start(button, expand=True, fill=True, padding=10)
                self.result.pack_start(result_box, expand=False, fill=False, padding=0)
            else:
                #self.__logger.info(":(")
                label = Gtk.Label("No student or lecturer found.")
                self.result.pack_start(label, expand=False, fill=False, padding=0)

        else:
            label = Gtk.Label("No student or lecturer found.")
            self.result.pack_start(label, expand=False, fill=False, padding=0)

        self.result.show_all()

    def create_series(self, ev=None):
        #self.__logger.info("creating series")

        for element in self.result.get_children():
            self.result.remove(element)

        loading_box = Gtk.Box(spacing=10)
        loading_box.set_name("grd_result_loading")

        label = Gtk.Label("")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        spinner = Gtk.Spinner()
        spinner.start()
        loading_box.pack_start(spinner, expand=False, fill=False, padding=0)

        label = Gtk.Label(" Creating user profile... ")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        label = Gtk.Label("")
        loading_box.pack_start(label, expand=False, fill=False, padding=0)

        self.result.pack_start(loading_box, expand=False, fill=False, padding=0)
        self.result.show_all()

        future = self.__session.post(self.__create_url + self.id, background_callback=self.set_series_close_modal)

    def set_series_close_modal(self, sess, resp):
        print resp.content
        if resp.ok:
            details = json.loads(resp.content, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))

            if details.identifier:
                self.series_id = details.identifier
                self.series_title = details.title
            else:
                self.series_id = ""
                self.series_title = ""

        self.close_modal()

    def close_modal(self, ev=None):
        self.__logger.info("closing modal")
        self.dialog.response(-10)