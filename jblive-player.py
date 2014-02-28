#!/usr/bin/env python2
# jblive-player -- Plays gs
#    Copyright (C) 2014 Eugene Miller <theerm@gmail.com>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#

import sys 
import os 
import time 
import thread 
import signal 
import urllib 
import gc
import gobject 
import pygst 
import pygtk 
import gtk 
import pango
import base64
import hashlib
import urlparse
from time import sleep
import m3u8
# gobject.threads_init()
pygst.require("0.10")
import gst

STOPPED = gst.STATE_NULL
PAUSED = gst.STATE_PAUSED
PLAYING = gst.STATE_PLAYING

def gtk_main_quit(*args, **kwargs):
    gtk.main_quit()
# [RTSP Stream] | [RTMP Stream] | [HLS Stream] | [iPhone Stream] | [Radio Stream]
streams = {
    'FM': 'http://jblive.fm/',
    'HLS' : 'http://jblive.videocdn.scaleengine.net/jb-live/play/jblive.stream/playlist.m3u8',
    'RTMP' : 'rtmp://jblive.videocdn.scaleengine.net/jb-live/play/jblive.stream',
    'RTSP': 'rtsp://jblive.videocdn.scaleengine.net/jb-live/play/jblive.stream',
}

class Player(gobject.GObject):
    __gsignals__ = {
        'error': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str,str)),
        'end-of-stream': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'show-window': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
        'state-changed': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (object,)),
        'tag-received': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, (str, object)),
        'missing-plugin': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ())
    }
    
    def __init__(self, filename=None):
        gobject.GObject.__init__(self)
        self.showing_controls = False
        self.filename = filename
        self.playing_state = STOPPED
        self.fullscreen = False
        self.init_window()
        self.init_invisible_cursor()
        self.init_main_event_box()
        self.init_main_vbox()
        self.init_stream_lable()
        self.init_movie_window()
        self.init_controls()
        self.init_logo_window()
        self.init_hide()
        self.init_player()

    def init_logo_window(self):
        self.logo_HBox = gtk.HBox()
        img = gtk.Image()
        img.set_from_file(os.path.join(sys.path[0], 'logo.png'))
        self.logo_HBox.pack_start(img, True, True)
        self.main_VBox.pack_start(self.logo_HBox, True, True)
        self.logo_HBox.show_all()

    def init_hide(self):
        self.window.show_all()
        self.controls.hide()
        self.movie_window.hide()
        self.logo_HBox.show_all()
        # self.window.hide()

    def init_invisible_cursor(self):
        pix_data = """/* XPM */
static char * invisible_xpm[] = {
"1 1 1 1",
"       c None",
" "};"""
        color = gtk.gdk.Color()
        pix = gtk.gdk.pixmap_create_from_data(None, pix_data, 1, 1, 1, color, 
                                              color)
        self.invisble_cursor = gtk.gdk.Cursor(pix, pix, color, color, 0, 0)

    def e_box_hbox(self):
        hb = gtk.HBox()
        e = gtk.EventBox()
        e.add(hb)
        e.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        return hb, e

    def init_fs_buttons(self):
        self.fs_button = gtk.Button('', gtk.STOCK_FULLSCREEN)
        self.unfs_button = gtk.Button('', gtk.STOCK_LEAVE_FULLSCREEN)
        hb, e = self.e_box_hbox()
        hb.pack_start(self.fs_button, False, False)
        hb.pack_start(self.unfs_button, False, False)
        self.fs_button.connect('clicked', self.toggle_full_screen)
        self.unfs_button.connect('clicked', self.toggle_full_screen)
        self.controls.pack_end(e, False, False)
        self.fs_button.hide()

    def init_stream_buttons(self):
        self.stream_buttons = {}
        hb, e = self.e_box_hbox()
        for stream_name, stream_url in streams.iteritems():
            self.stream_buttons[stream_name] = gtk.Button(stream_name, 
                                                          gtk.STOCK_MEDIA_PLAY)
            self.stream_buttons[stream_name].set_label(stream_name)
            self.stream_buttons[stream_name].set_use_stock(False)
            self.stream_buttons[stream_name].show()
            hb.pack_start(self.stream_buttons[stream_name], False, False)
            self.stream_buttons[stream_name].connect('clicked', 
                                                     self.play_stream, 
                                                     stream_name, 
                                                     stream_url)
        self.controls.pack_start(e, False, False)

    def play_stream(self, widget, label, uri):
        gtk.threads_leave()
        print "play_stream:", label, uri
        self.stream_label.set_text(label)
        self.filename = uri
        self.start()

    def init_controls(self):
        ### SET UP CONTROLS ###
        self.controls = gtk.HBox()
        self.init_stream_buttons()
        self.init_fs_buttons()
        self.main_VBox.pack_end(self.controls, False, True)
        #### END OF SETTING UP CONTROLS ## ##

    def init_movie_window(self):
        ## movie_window
        self.movie_window = gtk.DrawingArea()
        self.movie_window.modify_bg(gtk.STATE_NORMAL,gtk.gdk.color_parse("#000000"))
        self.movie_window.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
        self.movie_window.connect('motion-notify-event', self.show_controls)
        self.movie_window.show()
        self.main_VBox.pack_start(self.movie_window, True, True)

    def init_main_vbox(self):
        self.main_VBox = gtk.VBox()
        self.main_VBox.show()
        self.main_event_box.add(self.main_VBox)

    def init_main_event_box(self):
        self.main_event_box = gtk.EventBox()
        self.main_event_box.modify_fg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#FFFFFF"))
        self.main_event_box.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        self.main_event_box.connect('motion-notify-event', self.show_controls)
        self.window.add(self.main_event_box)

    def init_stream_lable(self):
        ## Time label ##
        self.stream_label = gtk.Label()
        self.stream_label.modify_fg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#FFFFFF"))
        self.stream_label.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        self.stream_label.set_property('xalign',1.0)
        self.stream_label.modify_font(pango.FontDescription("15"))
        self.main_VBox.pack_start(self.stream_label, False, True)
        self.stream_label.show()

    def init_player(self):
        self.player = gst.element_factory_make("playbin2", "player")
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.enable_sync_message_emission()
        bus.connect("message", self.on_message)
        bus.connect("sync-message::element", self.on_sync_message)
        self.connect('state-changed', self.show_hide_play_pause)
        self.hide_timeout = None

    def init_window(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        self.window.set_title("JBLive-Player")
        self.window.set_icon_from_file(os.path.join(sys.path[0], "tv.png"))
        self.window.connect("destroy", gtk_main_quit)
        self.window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK |
                               gtk.gdk.POINTER_MOTION_MASK |
                               gtk.gdk.BUTTON_PRESS_MASK |
                               gtk.gdk.SCROLL_MASK)
        self.window.connect('key-press-event', self.on_key_press)
        self.window.connect('motion-notify-event', self.show_controls)
        self.window.connect('button-press-event', self.pause)
        
        self.window.set_title("JB Live Stream Player")
        self.window.set_default_size(600, 400)
        self.window.connect("destroy", gtk_main_quit, "WM destroy")
        

    def state_to_string(self, state):
        if state == PLAYING:
            return "PLAYING"
        if state == PAUSED:
            return "PAUSED"
        if state == STOPPED:
            return "STOPPED"
        return "ERROR"
        
    def show_hide_play_pause(self,*args):
        if self.fullscreen:
            self.fs_button.hide()
            self.unfs_button.show()
        else:
            self.fs_button.show()
            self.unfs_button.hide()

    def toggle_full_screen(self, *args):
        if self.fullscreen:
            self.fullscreen = False
            self.window.unfullscreen()
            self.movie_window.window.set_cursor(None)
        else:
            self.fullscreen = True
            self.window.fullscreen()
            self.movie_window.window.set_cursor(self.invisble_cursor)
        
        self.show_hide_play_pause()
        self.window.emit('check-resize')
    
    def show_controls(self,*args):
        self.controls.show()
        self.stream_label.show()
        self.show_hide_play_pause()
        if self.hide_timeout:
            gobject.source_remove(self.hide_timeout)
            self.hide_timeout = None
        self.hide_timeout = gobject.timeout_add(3000, self.hide_controls)
        self.movie_window.window.set_cursor(None)
        self.showing_controls = True
        
        
    def hide_controls(self):
        self.showing_controls = False
        self.controls.hide()
        self.stream_label.hide()
        self.hide_timeout = None
        self.movie_window.window.set_cursor(self.invisble_cursor)
        
    def on_key_press(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname in ('f', 'F'):
            self.toggle_full_screen()

        if keyname in ('d', 'D'):
            if self.window.get_decorated():
                self.window.set_decorated(False)
            else:
                self.window.set_decorated(True)
            self.window.emit('check-resize')
                
        if keyname in ('Return', 'p', 'P', 'a', 'A', 'space'):
            self.show_controls()
            self.pause()

    def start(self,*args):
        print "="*80
        self.tags = {}
        gc.collect()
        if self.filename is None:
            stream_name = streams.keys()[0]
            self.play_stream(None, stream_name, streams[stream_name])
            return

        uri = self.filename
        if os.path.isfile(self.filename):
            self.filename = os.path.realpath(self.filename)
            uri = "file://" + urllib.quote(self.filename)
            uri = uri.replace("\\'", "%27")
            uri = uri.replace("'", "%27")

        if not uri:
            print "empty uri"
            return
        print "playing uri:", uri
        self.player.set_state(STOPPED)
        self.player.set_property("uri", uri)
        self.player.set_state(PLAYING)
        self.emit('state-changed', PLAYING)
        self.playing_state = self.player.get_state()[1]
        self.should_hide_window()

    def should_hide_window(self):
        if self.player.get_property('n-video') > 0:
            self.movie_window.show()
            self.logo_HBox.hide()
        else:
            self.movie_window.hide()
            self.logo_HBox.show()

    def stop(self):
        self.player.set_state(STOPPED)
    
    def pause(self, *args):
        self.playing_state = self.player.get_state()[1]
        if self.playing_state == STOPPED:
            self.start()
        elif self.playing_state == PLAYING:
            self.player.set_state(STOPPED)
        elif self.playing_state == PAUSED:
            self.player.set_state(PLAYING)
            
        self.playing_state = self.player.get_state()[1]
        self.emit('state-changed', self.playing_state)

    def debug_message(self, gst_message):
        attribs_to_check = [
            'parse_clock_lost', 'parse_clock_provide',
            'parse_duration', 'parse_error', 'parse_new_clock',
            'parse_segment_done', 'parse_segment_start',
            'parse_tag', 
            'parse_warning']

        for k in attribs_to_check:
            try:
                res = getattr(gst_message, k)()
                print "-"*40, gst_message.type, "-"*40
                print k, res
                print "-"*40, '/', gst_message.type, "-"*40
            except:
                pass

    
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_STATE_CHANGED:
            # print "on_message parse_state_changed()", message.parse_state_changed()
            return

        if t == gst.MESSAGE_STREAM_STATUS:
            # print "on_message parse_state_changed()", message.parse_state_changed()
            return

        if t == gst.MESSAGE_EOS:
            print "END OF STREAM"
            self.player.set_state(STOPPED)
            self.emit('end-of-stream')
            return 

        if t == gst.MESSAGE_ERROR:
            self.player.set_state(STOPPED)
            err, debug = message.parse_error()
            print "Error: '%s'" % err, "debug: '%s'" % debug
            if err == 'Resource not found.':
                print "RETURNING"
                return
            self.emit('error', err, debug)
            return

        if t == gst.MESSAGE_TAG:
            for key in message.parse_tag().keys():
                msg = message.structure[key]
                if isinstance(msg, (gst.Date, gst.DateTime)):
                    self.tags[key] = "%s" % msg
                elif key not in ('image','private-id3v2-frame', 'preview-image',
                                 'private-qt-tag'):
                    print "tags[%s]=%s" % (key, msg )
                    self.tags[key] = "%s" % msg
                else:
                    if key == 'image':
                        self.tags["image-raw"] = msg
                    elif key == "preview-image":
                        self.tags["preview-image-raw"] = msg
                    print "tags[%s]=%s" % (key,"[Binary]")
                    data = {}
                    if isinstance(msg, list):
                        for i, v in enumerate(msg):
                            data[i] = base64.b64encode(msg[i])
                            data["%s-raw" % i] = msg[i]
                    elif isinstance(msg, dict):
                        for k, v in enumerate(msg):
                            data[k] = base64.b64encode(msg[k])
                            data[k+"-raw"] = msg[k]
                    else:
                        print "%s" % msg[0:10]
                        data = base64.b64encode(msg)
                    self.tags[key] = data

                    print self.tags[key]

                self.emit('tag-received', key, message.structure[key])
                return
    
    def on_sync_message(self, bus, message):
        if message.structure is None:
            return
        message_name = message.structure.get_name()
        print "on_sync_message:",message_name
        
        if message_name == "prepare-xwindow-id":
            print "*"*80
            self.window.show_all()
            self.imagesink = message.src
            self.imagesink.set_property("force-aspect-ratio", True)
            self.imagesink.set_xwindow_id(self.movie_window.window.xid)
            if self.fullscreen:
                gobject.idle_add(self.window.fullscreen)
            gobject.idle_add(self.emit,'show-window')
        elif message_name == 'missing-plugin':
            print "MISSING PLUGGIN"
            self.emit('missing-plugin')
        if message_name == 'playbin2-stream-changed':
            print "-"*80
    


if __name__ == '__main__':
    gobject.threads_init()

    def on_playing_state_changed(p, state):
        if state == gst.STATE_PLAYING:
            ind.set_from_stock(gtk.STOCK_MEDIA_PLAY)
        elif state == gst.STATE_PAUSED:
            ind.set_from_stock(gtk.STOCK_MEDIA_STOP)

    def error_msg(player, msg,debug):
        print "ERROR MESSAGE:", msg, ',', debug
        if not os.path.isfile(player.filename):
            player.emit('end-of-stream')

    def on_menuitem_clicked(item):
        gtk.threads_leave()
        label = item.get_label()
        if label == 'Quit':
            gtk_main_quit()
        elif label in streams.keys():
            player.play_stream(None, label, streams[label])
            player.start()
        print "CLICKED:%s " % (item.get_label())

    def on_button_press(icon, event, **kwargs):
        print "on_button_press:",icon, event
        if event.button == 1:
            menu.popup(None, None, None, event.button, event.get_time())

    ind = gtk.StatusIcon()
    ind.set_name("jblive-player.py")
    ind.set_title("jblive-player.py")
    ind.connect("button-press-event", on_button_press)
    ind.set_from_stock(gtk.STOCK_MEDIA_STOP)
    
    menu = gtk.Menu()
    for k, v in streams.iteritems():
        img = gtk.image_new_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON)
        item = gtk.ImageMenuItem(k)
        item.set_image(img)
        item.show()
        item.connect("activate", on_menuitem_clicked)
        menu.append(item)

    quit_item = gtk.ImageMenuItem("Quit")
    quit_item.connect("activate", on_menuitem_clicked)
    img = gtk.image_new_from_stock(gtk.STOCK_QUIT, gtk.ICON_SIZE_BUTTON)
    quit_item.set_image(img)
    quit_item.show()
    menu.append(quit_item)
    
    prevFiles = []
    currentFile = []
    files = []
    args = sys.argv[1:]
    cwd = os.getcwd()
    shuffle = False

    for arg in args:
        if os.path.exists(arg) or arg.startswith("rtsp://") or \
           arg.startswith("rtmp://") or arg.startswith("http://"):
            print "file:%s" % arg
            files.append(arg)

    player = Player()
    player.connect('error', error_msg)
    player.connect('state-changed', on_playing_state_changed)

    while gtk.events_pending(): 
        gtk.main_iteration(False)
    gtk.main()


