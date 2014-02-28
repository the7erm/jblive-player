#!/usr/bin/env python2
# lib/player.py -- main gstreamer player
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
        self.showingControls = False
        self.filename = filename
        self.playingState = STOPPED
        self.play_thread_id = None
        self.fullscreen = False
        self.seek_locked = False
        self.pos_data = {}
        self.dur_int = 0
        self.pos_int = 0
        self.volume = 1.0
        self.time_format = gst.Format(gst.FORMAT_TIME)
        self.window = None
        self.main_event_box = None
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
        # self.window.set_icon_from_file(sys.path[0]+"/"+"tv.png")
        self.logo_HBox = gtk.HBox()
        img = gtk.Image()
        img.set_from_file(os.path.join(sys.path[0], 'logo.png'))
        self.logo_HBox.pack_start(img, True, True)
        self.mainVBox.pack_start(self.logo_HBox, True, True)
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
        pix = gtk.gdk.pixmap_create_from_data(None, pix_data, 1, 1, 1, color, color)
        self.invisble_cursor = gtk.gdk.Cursor(pix, pix, color, color, 0, 0)

    def init_play_buttons(self):
        self.prev_button = gtk.Button('',gtk.STOCK_MEDIA_PREVIOUS)
        self.pause_button = gtk.Button('',gtk.STOCK_MEDIA_PAUSE)
        self.play_button = gtk.Button('',gtk.STOCK_MEDIA_PLAY)
        self.next_button = gtk.Button('',gtk.STOCK_MEDIA_NEXT)

        hb = gtk.HBox()
        e = gtk.EventBox()
        e.add(hb)
        e.modify_bg(gtk.STATE_NORMAL,gtk.gdk.color_parse("#000000"))
        hb.pack_start(self.prev_button,False,False)
        hb.pack_start(self.pause_button,False,False)
        hb.pack_start(self.play_button,False,False)
        hb.pack_start(self.next_button,False,False)
        
        self.controls.pack_start(e, False, False)

    def init_fs_buttons(self):
        self.fs_button = gtk.Button('',gtk.STOCK_FULLSCREEN)
        self.unfs_button = gtk.Button('',gtk.STOCK_LEAVE_FULLSCREEN)
        hb = gtk.HBox()
        e = gtk.EventBox()
        e.add(hb)
        e.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        hb.pack_start(self.fs_button, False, False)
        hb.pack_start(self.unfs_button, False, False)
        self.fs_button.connect('clicked', self.toggle_full_screen)
        self.unfs_button.connect('clicked', self.toggle_full_screen)
        self.controls.pack_end(e, False, False)
        self.fs_button.hide()

    def init_stream_buttons(self):
        self.stream_buttons = {}
        hb = gtk.HBox()
        e = gtk.EventBox()
        e.add(hb)
        e.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        for stream_name, stream_url in streams.iteritems():
            print stream_name
            self.stream_buttons[stream_name] = gtk.Button(stream_name, gtk.STOCK_MEDIA_PLAY)
            self.stream_buttons[stream_name].set_label(stream_name)
            self.stream_buttons[stream_name].set_use_stock(False)
            self.stream_buttons[stream_name].show()
            hb.pack_start(self.stream_buttons[stream_name], False, False)
            self.stream_buttons[stream_name].connect('clicked', self.play_stream, stream_name, stream_url)
        self.controls.pack_start(e, False, False)

    def play_stream(self, widget, label, uri):
        print "play_stream:", label, uri
        self.stream_label.set_text(label)
        #if uri.endswith('.m3u8'):
        #    uri = self.get_uri_from_m3u8(uri)
        self.filename = uri
        self.start()

    def get_uri_from_m3u8(self, uri):
        m3u8_obj = m3u8.load(uri)
        print "segements:", m3u8_obj.segments
        print "duratio:", m3u8_obj.target_duration
        for playlist in m3u8_obj.playlists:
            print "playlist.uri:", playlist.uri
            print "playlist.stream_info.bandwidth:", playlist.stream_info.bandwidth
            print "playlist:",playlist
            return playlist.uri
        return uri

    def init_controls(self):
        ### SET UP CONTROLS ###
        self.controls = gtk.HBox()
        self.init_stream_buttons()
        # self.init_play_buttons()
        self.init_fs_buttons()
        self.mainVBox.pack_end(self.controls,False,True)
        #### END OF SETTING UP CONTROLS ## ##

    def init_movie_window(self):
        ## movie_window
        self.movie_window = gtk.DrawingArea()
        # gtk.DrawingArea()
        # self.movie_window.set_has_window(True)
        self.movie_window.modify_bg(gtk.STATE_NORMAL,gtk.gdk.color_parse("#000000"))
        self.movie_window.add_events(gtk.gdk.KEY_PRESS_MASK | gtk.gdk.POINTER_MOTION_MASK)
        # self.movie_window.connect('key-press-event', self.on_key_press)
        self.movie_window.connect('motion-notify-event',self.show_controls)
        self.movie_window.show()
        self.mainVBox.pack_start(self.movie_window, True, True)

    def init_main_vbox(self):
        self.mainVBox = gtk.VBox()
        self.mainVBox.show()
        self.main_event_box.add(self.mainVBox)

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
        self.mainVBox.pack_start(self.stream_label, False, True)
        self.stream_label.show()

    def init_player(self):
        self.player = gst.element_factory_make("playbin2", "player")
        vol = self.player.get_property("volume")
        # print "DEFAULT VOLUME:",vol
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
        self.window.set_icon_from_file(sys.path[0]+"/"+"tv.png")
        self.window.connect("destroy", gtk_main_quit)
        self.window.modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#000000"))
        self.window.add_events(gtk.gdk.KEY_PRESS_MASK |
                               gtk.gdk.POINTER_MOTION_MASK |
                               gtk.gdk.BUTTON_PRESS_MASK |
                               gtk.gdk.SCROLL_MASK)
        self.window.connect('key-press-event', self.on_key_press)
        self.window.connect('motion-notify-event', self.show_controls)
        # self.window.connect('button-press-event', self.show_controls)
        self.window.connect('button-press-event', self.pause)
        # self.window.connect('key-press-event', self.show_controls)
        self.window.connect("scroll-event", self.on_scroll)
        
        self.window.set_title("JB Live gdvPlayer")
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
        """
        if self.playingState in (STOPPED, PAUSED):
            self.play_button.show()
            self.pause_button.hide()
        else:
            self.play_button.hide()
            self.pause_button.show()
        """
        if self.fullscreen:
            self.fs_button.hide()
            self.unfs_button.show()
        else:
            self.fs_button.show()
            self.unfs_button.hide()
        """
        self.next_button.show()
        self.prev_button.show()
        """

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
        
    
    def on_scroll(self, widget, event):
        return
        print "on_scroll:"
        gtk.gdk.threads_leave()
        if event.direction == gtk.gdk.SCROLL_UP:
            self.seek("+5")
        if event.direction == gtk.gdk.SCROLL_DOWN:
            self.seek("-5")
        print "/on_scroll"

    def ind_on_scroll(self, widget, steps, direction):
        if direction == 0:
            self.seek("+5")
        else:
            self.seek("-5")
    
    def show_controls(self,*args):
        # print "show_controls"
        
        self.controls.show()
        self.stream_label.show()
        self.show_hide_play_pause()
        if self.hide_timeout:
            gobject.source_remove(self.hide_timeout)
            self.hide_timeout = None
        self.hide_timeout = gobject.timeout_add(3000, self.hide_controls)
        # if self.fullscreen:
        self.movie_window.window.set_cursor(None)
        self.showingControls = True
        
        
    def hide_controls(self):
        self.showingControls = False
        self.controls.hide()
        self.stream_label.hide()
        self.hide_timeout = None
        #if self.fullscreen:
        self.movie_window.window.set_cursor(self.invisble_cursor)
        
    def on_key_press(self, widget, event):
        keyname = gtk.gdk.keyval_name(event.keyval)
        if keyname in ('f','F'):
            self.toggle_full_screen()

        if keyname in ('d','D'):
            if self.window.get_decorated():
                self.window.set_decorated(False)
            else:
                self.window.set_decorated(True)
            self.window.emit('check-resize')
                
        if keyname in ('Return','p','P','a','A','space'):
            self.show_controls()
            self.pause()
            
        if keyname == 'Up':
            self.seek("+5")
        
        if keyname == 'Down':
            self.seek("-5")
            
        if keyname == 'Right':
            self.next_button.emit('clicked')
        
        if keyname == 'Left':
            self.prev_button.emit('clicked')
        
            
    def next(self, *args, **kwargs):
        self.next_button.emit("clicked")

    def prev(self, *args, **kwargs):
        self.prev_button.emit('clicked')

    def start(self,*args):
        print "="*80
        # self.play_thread_id = None
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
            uri = uri.replace("\\'","%27")
            uri = uri.replace("'","%27")

        if uri == "":
            print "empty uri"
            return
        print "playing uri:",uri
        self.player.set_state(STOPPED)
        self.player.set_property("uri", uri)
        # self.player.set_property("volume",self.volume)
        self.player.set_state(PLAYING)
        self.emit('state-changed', PLAYING)
        self.playingState = self.player.get_state()[1]
        try:
            self.dur_int = self.player.query_duration(self.time_format, None)[0]
        except gst.QueryError, e:
            print "gst.QueryError:",e
            self.dur_int = 0

        self.update_time()
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
        
    def set_volume(self,widget,value):
        self.volume = value
        print "set_volume:",self.volume
        # self.player.set_property("volume",self.volume)
        
    def convert_ns(self, time_int):
        time_int = time_int / 1000000000

        _hours = time_int / 3600
        time_int = time_int - (_hours * 3600)
        _mins = time_int / 60
        time_int = time_int - (_mins * 60)
        _secs = time_int
        
        if _hours:
            return "%d:%02d:%02d" % (_hours, _mins, _secs)

        if _mins:
            return "%d:%02d" % (_mins, _secs)

        return "0:%02d" % (_secs)

        

    def update_time(self, retry=True):
        #if self.playingState != PLAYING :
        #    print "update_time:NOT PLAYING"
        #    return True

        # print 'update_time';
        try:
            dur_int = self.player.query_duration(self.time_format, None)[0]
            dur_str = self.convert_ns(dur_int)
            self.dur_int = dur_int
        except:
            return True
        
        try:
            pos_int = self.player.query_position(self.time_format, None)[0]
        except:
            pos_int = 0

        if pos_int == 0 and retry:
            sleep(0.1)
            self.update_time(retry=False)
            return True
            
        pos_str = self.convert_ns(pos_int)
        left_int = (dur_int - pos_int)
        left_str = self.convert_ns(left_int)
        decimal = float(pos_int) / dur_int
        percent = "%.2f%%" % (decimal * 100)
        try:
            # print pos_int, dur_int, left_int, decimal, pos_str, dur_str, left_str, percent
            self.pos_int = pos_int
            self.left_int = left_int
            self.emit('time-status', pos_int, dur_int, left_int, decimal, pos_str, dur_str, left_str, percent)
            self.pos_data = {
                "pos_str": pos_str, 
                "dur_str": dur_str, 
                "left_str": left_str,
                "percent": percent,
                "pos_int": pos_int,
                "dur_int": dur_int,
                "left_int": left_int,
                "decimal": decimal,
                "min": 0,
                "max": dur_int,
                "value": pos_int,
                "playingState": self.state_to_string(self.playingState)
            }
        except TypeError, e:
            print "TypeError:",e
        
        return True
        
    def pause(self, *args):
        self.playingState = self.player.get_state()[1]
        if self.playingState == STOPPED:
            self.start()
        elif self.playingState == PLAYING:
            self.player.set_state(PAUSED)
        elif self.playingState == PAUSED:
            self.player.set_state(PLAYING)
            
        self.playingState = self.player.get_state()[1]
        self.emit('state-changed', self.playingState)
        self.update_time()


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
                print "-"*40,gst_message.type,"-"*40
                print k, res
                print "-"*40,'/',gst_message.type,"-"*40
            except:
                pass

    
    def on_message(self, bus, message):
        t = message.type
        # print "on_message:",t
        # self.debug_message(message)
        if t == gst.MESSAGE_STATE_CHANGED:
            # print "on_message parse_state_changed()", message.parse_state_changed()
            return

        if t == gst.MESSAGE_STREAM_STATUS:
            # print "on_message parse_state_changed()", message.parse_state_changed()
            return

        if t == gst.MESSAGE_EOS:
            print "END OF STREAM"
            # self.play_thread_id = None
            self.player.set_state(STOPPED)
            self.emit('end-of-stream')
            return 

        if t == gst.MESSAGE_ERROR:
            # self.play_thread_id = None
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
            # self.window.show_now()
            # self.window.set_decorated(True)
            # self.clear_hide_timeout()
            # gtk.gdk.threads_enter()
            self.window.show_all()
            self.imagesink = message.src
            self.imagesink.set_property("force-aspect-ratio", True)
            self.imagesink.set_xwindow_id(self.movie_window.window.xid)
            if self.fullscreen:
                gobject.idle_add(self.window.fullscreen)
            # self.window.show()
            # gtk.gdk.threads_leave()
            gobject.idle_add(self.emit,'show-window')
        elif message_name == 'missing-plugin':
            print "MISSING PLUGGIN"
            # self.play_thread_id = None
            # self.player.set_state(STOPPED)
            self.emit('missing-plugin')
        if message_name == 'playbin2-stream-changed':
            print "-"*80

            
    def control_seek(self,w,seek):
        print "control_seek:",seek
        self.seek(seek)
        
    
    def seek_ns(self,ns):
        print "SEEK_NS:",ns
        ns = int(ns)
        print "SEEK_NS:",ns
        self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, ns)
        self.update_time()
    
    def seek(self, string):
        if self.pos_int <= 0:
            print "self.pos_int <= 0"
            return
        if self.seek_locked:
            return
        self.seek_locked = True
        
        # print "player.seek:",string
        string = str(string)
        string = string.strip()
        firstChar = string[0]
        lastChar = string[-1]
        seek_ns = None
        
        if firstChar in ('+','-'):
            # skip ahead x xeconds
            skip_second = int(string[1:]) * 1000000000
            if firstChar == '+':
                seek_ns = self.pos_int + skip_second
            else:
                seek_ns = self.pos_int - skip_second
        elif lastChar == '%':
            seek_ns = int(float(string[0:-1]) * 0.01 * self.dur_int)
        else:
            seek_ns = int(string) * 1000000000
        
        #if not seek_ns:
        #    self.seek_locked = False
        #    return
        
        if seek_ns < 0:
            seek_ns = 0
        elif seek_ns > self.dur_int:
            self.seek_locked = False
            return
        
        try:
            self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)
        except:
            print "ERROR SEEKING"
            self.seek_locked = False
            return
            
        self.pos_int = seek_ns
        print "SEEK_NS:",seek_ns
        """
        left_int = (self.dur_int - seek_ns)
        pos_str = self.convert_ns(seek_ns)
        dur_str = self.convert_ns(self.dur_int)
        left_str = self.convert_ns(left_int)
        decimal = float(seek_ns) / self.dur_int
        percent = "%.2f%%" % (decimal * 100)
        try:
            self.emit('time-status', seek_ns, self.dur_int, left_int, decimal, pos_str, dur_str, left_str, percent)
        except TypeError, e:
            print "TypeError:",e
        """
        self.seek_locked = False


if __name__ == '__main__':
    gobject.threads_init()
    
    def error_msg(player, msg,debug):
        print "ERROR MESSAGE:", msg, ',', debug
        if not os.path.isfile(player.filename):
            player.emit('end-of-stream')

    def on_menuitem_clicked(item):
        # CLICKED:(<gtk.ImageMenuItem object at 0x8f6bb44 (GtkImageMenuItem at 0x8bc40f8)>,) {}
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
        

    import random
    #ind = appindicator.Indicator("fmp-player-cmd-indicator",
    #                                   gtk.STOCK_CDROM,
    #                                   appindicator.CATEGORY_APPLICATION_STATUS)
    ind = gtk.StatusIcon()
    ind.set_name("player.py")
    ind.set_title("player.py")
    ind.connect("button-press-event", on_button_press)
    ind.set_from_stock(gtk.STOCK_MEDIA_PLAY)

    
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
        if os.path.exists(arg) or arg.startswith("rtsp://") or arg.startswith("rtmp://"):
            print "file:%s" % arg
            files.append(arg)
        elif arg in ('-s','--shuffle','-shuffle'):
            shuffle = True
            
    
    if shuffle:
        print "SHUFFLE"
        random.shuffle(files)

    player = Player()
    #  player.connect('end-of-stream', next)
    player.connect('error', error_msg)
    ind.connect('scroll-event', player.on_scroll)

    # player.next_button.connect('clicked',next)
    # player.prev_button.connect('clicked',prev)
    # gobject.idle_add(next)
    while gtk.events_pending(): gtk.main_iteration(False)
    gtk.main()

