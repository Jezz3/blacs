#####################################################################
#                                                                   #
# /plugins/delete_repeated_shots/__init__.py                        #
#                                                                   #
# Copyright 2017, JQI                                               #
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
from queue import Queue

import h5py

from qtutils import UiLoader

from labscript_utils.shared_drive import path_to_agnostic
from labscript_utils.ls_zprocess import Lock
from blacs.plugins import PLUGINS_DIR
from PyQt5.QtCore import pyqtSignal,QObject

name = "show axes parameters"
module = "axes" # should be folder name
logger = logging.getLogger('BLACS.plugin.%s'%module)

class Plugin(QObject):
    # Define a signal that passes a string (the output text)
    update_text_signal = pyqtSignal(str)

    def __init__(self, initial_settings):
        super().__init__()

        self.menu = None
        self.notifications = {}
        self.initial_settings = initial_settings
        self.BLACS = None
        self.ui = None

        # Connect the signal to the slot that updates the textEdit
        self.update_text_signal.connect(self.update_text_edit)
        
    def plugin_setup_complete(self, BLACS):
        self.BLACS = BLACS

        # Add our controls to the BLACS UI:
        self.ui = UiLoader().load(os.path.join(PLUGINS_DIR, module, 'controls.ui'))
        BLACS['ui'].queue_controls_frame.layout().addWidget(self.ui)

        self.ui.textEdit.setText("")

    def on_shot_complete(self, h5_filepath):
        #Open the HDF5 file in read mode
        with h5py.File(h5_filepath, 'r') as hdf:
            # Navigate to the specific path in the file
            globals_group = hdf["/globals"]
            all_group = {name for name,_ in globals_group.items()}  
            matching_attributes = {}
            for group in all_group:
                path = f'/globals/{group}/expansion'
                dataset = hdf[path]
                # Iterate through the attributes and find those with the value "outer"
                matching_attributes.update({attr: value for attr, value in dataset.attrs.items() if value == 'outer'})
                print(f"matching_attributes: {matching_attributes}")
                globals_group = hdf['/globals']
                output_text = ""

            for attr in matching_attributes:
                if attr in globals_group.attrs:
                    value = globals_group.attrs[attr]
                    axes = matching_attributes[attr]
                    output_text += f"'{attr}' : {value}, {axes}\n"
                else:
                    output_text += f"Attribute '{attr}' not found in /globals\n"

       # Emit the signal with the output_text
        self.update_text_signal.emit(output_text)

    def update_text_edit(self, text):
        self.ui.textEdit.setText(text)

    def get_save_data(self):
        return
    
    def get_callbacks(self):
        return {'shot_complete': self.on_shot_complete}

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
        