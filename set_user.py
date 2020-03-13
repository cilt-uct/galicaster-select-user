"""Copyright (C) 2018  The University of Cape Town

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
import requests
from collections import namedtuple
from datetime import timedelta, datetime, tzinfo
from string import Template

gi.require_version('Gtk', '3.0')

from gi.repository import Gtk, Gdk, GdkPixbuf, GObject, Pango, GLib
from galicaster.core import context
from galicaster.classui import get_ui_path
from galicaster.classui import get_image_path
from galicaster.classui.elements.message_header import Header
from galicaster.mediapackage import mediapackage
from galicaster.utils.i18n import _

# This is the name of this plugin's section in the configuration file
CONFIG_SECTION = "set_user"

# REGEXP Defaults and Keys
DEFAULT_REGEXP = "[0-9]{8}|[a-zA-Z]{6}[0-9]{3}|[T|t][0-9]{7}"
CONFIG_REGEXP = "rexexp"

DEFAULT_SERIES_FILTER = '%2Csubject%3APersonal'
CONFIG_SERIES_FILTER = "filter"

METADATA = Template('[]')
ACL = Template('[]')

def init():
    global recorder, dispatcher, logger, config, repo, oc_client, METADATA, ACL

    config = context.get_conf().get_section(CONFIG_SECTION) or {}
    dispatcher = context.get_dispatcher()
    repo = context.get_repository()
    logger = context.get_logger()
    recorder = context.get_recorder()
    oc_client = context.get_occlient()

    with open(get_ui_path("series_metadata_template.json"), "r") as metadataFile:
        METADATA = Template(metadataFile.read())

    with open(get_ui_path("acl_template.json"), "r") as aclFile:
        ACL = Template(aclFile.read())

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

    recorder_ui = context.get_mainwindow().nbox.get_nth_page(0)

    controller = UserController(logger, recorder_ui, oc_client)

    logger.info("Set user init done.")

class UserController():
    """
    Handle the buttons on the main ui
    """
    def __init__(self, _logger, _ui , _client):
        self.__logger = _logger
        self.__ui = _ui
        self.__oc_client = _client

        self.details = None
        self.__ui.connect('key-press-event', self.on_key_press)

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

    def on_key_press(self, widget, event):
        global recorder
        #logger.info("Key press on widget: {}".format(widget))
        #logger.info("          Modifiers: {}".format(event.state))
        logger.info("      Key val, name: {} {}".format(event.keyval, Gdk.keyval_name(event.keyval)))

        if (Gdk.keyval_name(event.keyval) == "Return"):
            logger.info("      ENTER :) {}".format(recorder.is_recording()))
            if recorder.is_recording():
                self.stop_recording()
            else:
                self.on_rec()

            return True

    def button_set_user(self, button):
        self.__logger.info("SET USER")
        popup = SetUserClass(self.__logger, title="Get My Info", client = self.__oc_client)

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
            recorder.title_standin = "Live with " + self.details['organizer']

        if popup.return_value == -7:
            self.__logger.info("Cancelled")

    def button_clear_user(self, button):
        self.__logger.info("CLEAR USER")
        self.details = None
        self.btn_clear.set_sensitive(False) # disabled
        self.btn_show.set_label("Select a user...")
        self.title.set_text(_("No upcoming events"))
        self.box.show_all()
        recorder.title_standin = None

    def on_rec(self, element = None):
        global recorder

        self.__logger.info("# Start Recording 1")
        current_mediapackage = self.create_mp()
        if current_mediapackage is None:
            self.__logger.info("# MP NONE")
        else:
            self.__logger.info(current_mediapackage.getTitle())
            self.__logger.info(current_mediapackage.getSeries())

        recorder.record(current_mediapackage)
        self.__logger.info("# Start Recording 2")

    def stop_recording(self, element = None, mp = None):
        global recorder
        self.__logger.info("# Stopping Recording")
        Gdk.threads_add_idle(GLib.PRIORITY_HIGH, recorder.stop)

    def create_mp(self):
        if self.details is None:
            return self.default_mediapackage()

        self.details['take'] += 1
        # self.__logger.info(self.details)
        title = self.details['organizer'] + ' - Take #' + str(self.details['take'])
        # self.__logger.info(title)

        new_mp = mediapackage.Mediapackage(title=title, presenter=self.details['organizer'])
        new_mp.setMetadataByName('source', 'Personal['+ self.details['series'] +']')
        new_mp.setSeries({
            'title': self.details['seriesTitle'],
            'identifier': self.details['series']
        })
        # self.__logger.info(new_mp.getTitle())
        return new_mp

    def default_mediapackage(self):
        global config

        now = datetime.now().replace(microsecond=0)
        title = "Recording started at " + now.isoformat()
        mp = mediapackage.Mediapackage(title=title)
        if (context):
            mp.setSeries({
                'identifier': context.get_conf().get('series', 'default')
            })
        return mp

class SetUserClass(Gtk.Widget):
    """
    Handle a pop up to select a user
    """
    __gtype_name__ = 'SetUserClass'

    def __init__(self, _logger=None, title="Get My Info", client=None):
        """
        """
        self.id = ""
        self.user_name = ""
        self.user_email = ""
        self.series_id = ""
        self.series_title = ""
        self.searching = False
        self.details = None

        self.__logger = _logger
        self.__oc_client = client

        self.series_filter = config.get(CONFIG_SERIES_FILTER, DEFAULT_SERIES_FILTER)

        regexp = config.get(CONFIG_REGEXP, DEFAULT_REGEXP)
        self.__logger.info("REGEXP = " + regexp)
        self.__regexp = re.compile(regexp)

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

        # user select button
        self.user_button = Gtk.Button()

        #NEW HEADER
        strip = Header(size=size, title=title)
        self.dialog.vbox.pack_start(strip, True, True, 0)
        self.dialog.vbox.reorder_child(strip, 0)

        self.search_field = gui.get_object("inp_search")
        #search_field.connect('key-press-event', self.on_key_press)
        self.search_field.connect('key-release-event', self.on_key_release)
        #self.search_field.connect('search-changed', self.search_changed)
        #self.search_field.connect('stop-search', self.search_stopped)

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

        # If Escape pressed, reset text
        if ev.keyval == Gdk.KEY_Escape:
            widget.set_text("")
            self.clear_search_entry()

        # If Enter pressed, try searching
        if ev.keyval == Gdk.KEY_Return or ev.keyval == Gdk.KEY_KP_Enter:
            self.do_search(widget.get_text())

        if self.__regexp.match(widget.get_text()): # if valid search
            self.__logger.info("found :) " + widget.get_text())
            if not self.searching:
                self.do_search(widget.get_text())

    def search_changed(self, widget, data=None):
        #self.__logger.info("search_changed")

        if widget.get_text() == "":
            self.clear_search_entry()

        if self.__regexp.match(widget.get_text()): # if valid search
            #self.__logger.info("found :) " + widget.get_text())
            if not self.searching:
                self.do_search(widget.get_text())

    def search_stopped(self, widget, data=None):
        #self.__logger.info("search_stopped")
        self.clear_search_entry()
        self.searching = False

    def clear_search_entry(self):
        self.searching = False
        self.search_field.set_text("")

        for element in self.result.get_children():
            self.result.remove(element)

        label = Gtk.Label("")
        self.result.pack_start(label, expand=False, fill=False, padding=0)

    def do_search(self, value):
        self.__logger.info("Searching for " + value)
        self.searching = True
        self.search_field.set_editable(False) # disabled

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

        self.show_response( self.call_get_user_info(value) ) # static request

    def show_response(self, details):
        self.__logger.info("Got search results back")

        for element in self.result.get_children():
            self.result.remove(element)

        if details['fullname']:
            self.details = details
            self.id = details['username']
            self.user_name = details['fullname']
            self.user_email = details['email']

            result_box = Gtk.Box(spacing=30)
            result_box.set_name("grd_result_button")

            self.user_button = Gtk.Button()
            self.user_button.set_name("btn_select_user")
            self.user_button.set_relief(Gtk.ReliefStyle.NONE)
            button_box = Gtk.Box(spacing=10)
            self.user_button.add(button_box)

            self.__logger.info("Found: " + details['fullname'])
            label = Gtk.Label(details['fullname'])

            img_series = Gtk.Image()

            if details['ocSeries']:
                self.__logger.info("     Series: " + details['ocSeries'][0]['identifier'])
                img_series.set_from_icon_name("object-select-symbolic", 2)
                self.user_button.connect("clicked", self.close_modal)
                self.series_id = details['ocSeries'][0]['identifier']
                self.series_title = details['ocSeries'][0]['title']
            else:
                img_series.set_from_icon_name("star-new-symbolic", 2)
                self.user_button.connect("clicked", self.create_series)
                self.series_id = ""
                self.series_title = ""

            button_box.pack_start(img_series, expand=False, fill=False, padding=10)
            button_box.pack_start(label, expand=False, fill=False, padding=10)

            label = Gtk.Label("select")
            label.set_markup('<span foreground="#494941" face="sans" size="small">select</span>')
            button_box.pack_start(label, expand=False, fill=False, padding=10)

            result_box.pack_start(self.user_button, expand=True, fill=True, padding=10)
            self.result.pack_start(result_box, expand=False, fill=False, padding=0)
        else:
            self.__logger.info(":(")
            self.details = None
            label = Gtk.Label("No student or lecturer found.")
            self.result.pack_start(label, expand=False, fill=False, padding=0)

        self.searching = False
        self.search_field.set_editable(True) # enabled
        self.result.show_all()

    def create_series(self, ev=None):
        conf = context.get_conf()

        self.__logger.info("Creating series")

        if self.user_button is not None:
            self.user_button.set_sensitive(False) # disabled

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

        self.set_series_close_modal(self.call_create_series(self.details))

    def set_series_close_modal(self, resp):
        self.__logger.info("POST request returned.")

        if resp is not None:
            self.series_id = resp
            self.series_title = "Created Series: " + resp
            self.close_modal()
        else:
            self.series_id = ""
            self.series_title = ""

            for element in self.result.get_children():
                self.result.remove(element)

            loading_box = Gtk.Box(spacing=10)
            loading_box.set_name("grd_result_loading")

            label = Gtk.Label("")
            loading_box.pack_start(label, expand=False, fill=False, padding=0)

            img_error = Gtk.Image()
            img_error.set_from_icon_name("emblem-important", 5)
            loading_box.pack_start(img_error, expand=False, fill=False, padding=8)

            label = Gtk.Label("Could not create user profile")
            loading_box.pack_start(label, expand=False, fill=False, padding=0)

            label = Gtk.Label("")
            loading_box.pack_start(label, expand=False, fill=False, padding=0)

            self.result.pack_start(loading_box, expand=False, fill=False, padding=0)
            self.result.show_all()

    def close_modal(self, ev=None):
        self.__logger.info("closing modal")
        self.dialog.response(-10)

    def call_get_user_info(self, user_id):
        """
        Retreive user and series info from Opencast

        :param id: Staff / T / Student Number

        :return: Return dictionary structured content to set display name and series

        :raise ValueError: if the input arguments are not valid
        :raise OpencastException: if the communication to the opencast server fails
                                or an unexpected error occures
        """
        if not user_id:
            raise ValueError("user ID isn't set")

        result_data = {'fullname': '', 'email': '', 'username': '', 'site_id' : '', 'ocSeries' : [],
                       'ca_name': self.__oc_client.hostname}

        try:
            response = self.__oc_client.get_user_details(user_id)
            full_data = json.loads(response, encoding='utf8')
            # self.__logger.info(full_data)

            if full_data['user']['name']:
                result_data['fullname'] = full_data['user']['name']
                result_data['email'] = full_data['user']['email'].lower()
                result_data['username'] = full_data['user']['username'].lower()
                result_data['upperuser'] = full_data['user']['username'].upper()

        except Exception as exc:
            self.__logger.warning('call_get_user_info user [{1}]: {0}'.format(exc, user_id))


        try:
            response = self.__oc_client.get_personal_series(user_id, self.series_filter)

            if "Personal Series" in response:
                series_data = json.loads(response, encoding='utf8')

                if len(series_data) > 0:
                    result_data['ocSeries'] = series_data

        except Exception as exc:
            self.__logger.error('call_get_user_info series [{1}]: {0}'.format(exc, user_id))

        # self.__logger.info(result_data)
        return result_data

    def call_create_series(self, data):
        """
        Create a new Opencast Series with the data given

        :param data: Contains info about the series to be created

        :return: Return dictionary structured content to set display name and series

        :raise ValueError: if the input arguments are not valid
        :raise OpencastException: if the communication to the opencast server fails
                                or an unexpected error occures
        """
        global METADATA, ACL

        if not data:
            raise ValueError("user data isn't set")

        result = None
        try:
            m = METADATA.safe_substitute(data).encode('iso-8859-1')
            a = ACL.safe_substitute(data).encode('iso-8859-1')

            response = self.__oc_client.create_series(m, a)
            if response is not None:
                if "identifier" in response:
                    details = json.loads(response, object_hook=lambda d: namedtuple('X', d.keys())(*d.values()))
                    if details.identifier:
                        result = details.identifier

        except Exception as exc:
            self.__logger.error('call_create_series: {}'.format(exc))

        return result