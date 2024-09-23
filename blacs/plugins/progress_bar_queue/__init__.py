#####################################################################
#                                                                   #
# /plugins/progress_bar/__init__.py                                 #
#                                                                   #
# Copyright 2018, Christopher Billington                            #
#                                                                   #
# This file is part of the program BLACS, in the labscript suite    #
# (see http://labscriptsuite.org), and is licensed under the        #
# Simplified BSD License. See the license.txt file in the root of   #
# the project for the full license.                                 #
#                                                                   #
#####################################################################
import logging
import os
import subprocess
import threading
import sys
import time
from queue import Queue, Empty

import numpy as np

from qtutils import UiLoader, inmain, inmain_decorator
from qtutils.qt import QtGui, QtWidgets, QtCore

import labscript_utils.h5_lock
import h5py

import labscript_utils.properties as properties
from labscript_utils.connections import ConnectionTable
from zprocess import TimeoutError
from labscript_utils.ls_zprocess import Event
from blacs.plugins import PLUGINS_DIR, callback

name = "Progress Bar Queue"
module = "progress_bar_queue" # should be folder name
logger = logging.getLogger('BLACS.plugin.%s'%module)

# The progress bar will update every UPDATE_INTERVAL seconds, or at the marker
# times, whichever is soonest after the last update:
UPDATE_INTERVAL = 0.02
BAR_MAX = 100

class Plugin(object):
    def __init__(self, initial_settings):
        self.menu = None
        self.notifications = {}
        self.initial_settings = initial_settings
        self.BLACS = None
        self.command_queue = Queue()
        self.h5_filepath = None
        self.wait_completed_events_supported = False
        self.wait_completed = Event('wait_completed', role='wait')
        self.mainloop_thread = threading.Thread(target=self.mainloop)
        self.mainloop_thread.daemon = True
        
    def plugin_setup_complete(self, BLACS):
        self.BLACS = BLACS
        self.ui = UiLoader().load(os.path.join(PLUGINS_DIR, module, 'controls.ui'))
        self.bar = self.ui.bar
        self.style = QtWidgets.QStyleFactory.create('Fusion')
        if self.style is None:
            # If we're on Qt4, fall back to Plastique style:
            self.style = QtWidgets.QStyleFactory.create('Plastique')
        if self.style is None:
            # Not sure what's up, but fall back to app's default style:
            self.style = QtWidgets.QApplication.style()
        self.bar.setStyle(self.style)
        self.bar.setMaximum(BAR_MAX)
        self.bar.setAlignment(QtCore.Qt.AlignCenter)
        # Add our controls to the BLACS gui:
        BLACS['ui'].queue_status_verticalLayout.insertWidget(0, self.ui)

        self.ui.wait_warning.hide()
        self.mainloop_thread.start()

    def get_save_data(self):
        return {}
    
    def get_callbacks(self):
        return {'science_over': self.on_science_over,
                'science_starting': self.on_science_starting}
        
    # This callback should be run after any callbacks that might have significant time
    # delays. For example it should run after the cycle_time science_starting callback.
    # The priority should be set accordingly.
    @callback(priority=200)
    def on_science_starting(self, h5_filepath):
        # Tell the mainloop that we're starting a shot:
        self.command_queue.put(('start', h5_filepath))

    @callback(priority=5)
    def on_science_over(self, h5_filepath):
        # Tell the mainloop we're done with this shot:
        self.command_queue.put(('stop', None))

    @inmain_decorator(True)
    def clear_bar(self):
        self.bar.setEnabled(False)
        self.bar.setFormat('No shot running')
        self.bar.setValue(0)
        self.bar.setPalette(self.style.standardPalette())
        self.ui.wait_warning.hide()

    @inmain_decorator(True)
    def update_bar_value(self, marker=False, wait=False):
        """Update the progress bar with the current time elapsed. If marker or wait is
        true, then use the exact time at which the next marker or wait is defined,
        rather than the current time as returned by time.time()"""
        self.bar.setEnabled(True)       
        value = int(round(self.current_run / self.total_runs * BAR_MAX))
        self.bar.setValue(value)

        text = f'{value}%/{BAR_MAX}%'
        # if self.bar_text_prefix is not None:
        #     text = self.bar_text_prefix + text
        self.bar.setFormat(text)

    def _start(self, h5_filepath):
        """Called from the mainloop when starting a shot"""
        self.h5_filepath = h5_filepath
        # Get the stop time, any waits and any markers from the shot:
        with h5py.File(h5_filepath, 'r') as hdf:
            # Navigate to the specific path in the file
            globals_group = hdf["/"]
            self.total_runs = globals_group.attrs["n_runs"]
            self.current_run = globals_group.attrs["run number"]

            print(self.total_runs)
            print(self.current_run)

    def _stop(self):
        """Called from the mainloop when ending a shot"""
        self.h5_filepath = None

    def mainloop(self):
        running = False
        self.clear_bar()
        while True:
            try:
                if running:
                    try:
                        command, h5_filepath = self.command_queue.get(timeout=0.5)
                    except Empty:
                        continue
                else:
                    command, h5_filepath = self.command_queue.get()
                if command == 'close':
                    break
                elif command == 'start':
                        running = True
                        self._start(h5_filepath)
                        self.update_bar_value()
                elif command == 'stop':
                    if self.current_run == self.total_runs-1:
                        self.clear_bar()
                        running = False
                        self._stop()
                    else:
                        continue
                else:
                    raise ValueError(command)
            except Exception:
                logger.exception("Exception in mainloop, ignoring.")
                # Stop processing of the current shot, if any.
                self.clear_bar()
                inmain(self.bar.setFormat, "Error in progress bar plugin")
                running = False
                self._stop()
    
    def close(self):
        self.command_queue.put(('close', None))
        self.mainloop_thread.join()

    # The rest of these are boilerplate:
    def get_menu_class(self):
        return None
        
    def get_notification_classes(self):
        return []
        
    def get_setting_classes(self):
        return []
    
    def set_menu_instance(self, menu):
        self.menu = menu
        
    def set_notification_instances(self, notifications):
        self.notifications = notifications
        
    
