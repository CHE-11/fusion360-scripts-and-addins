# Application Global Variables
# This module serves as a way to share variables across different
# modules (global variables).

import os

# Flag that indicates to run in Debug mode or not. When running in Debug mode
# more information is written to the Text Command window. Generally, it's useful
# to set this to True while developing an add-in and set it to False when you
# are ready to distribute it.
DEBUG = True

REACT_DEV = True

# Gets the name of the add-in from the name of the folder the py file is in.
# This is used when defining unique internal names for various UI elements 
# that need a unique name. It's also recommended to use a company name as 
# part of the ID to better ensure the ID is unique.
ADDIN_NAME = 'ProParams'
COMPANY_NAME = 'CHE'

# Palettes
sample_palette_id = f'{COMPANY_NAME}_{ADDIN_NAME}_palette_id'


# See above
if REACT_DEV:
  parameter_table_palette_url = 'http://localhost:3000/'


# Name for a directory in user home to store data
user_dir_name = f'{ADDIN_NAME}'
USER_DIR_PATH = os.path.join(os.path.expanduser('~'), user_dir_name)
if not os.path.exists(USER_DIR_PATH):
    os.mkdir(USER_DIR_PATH)
    
# Design Workspace
design_workspace = 'FusionSolidEnvironment'

# Shared CHE panels, inserted after the named panel.
# SketchTab is contextual and shows while a sketch is being edited.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SketchTab', 'CHE_SketchPanel', 'SketchConstraintsPanel'),
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)

# Tabs
design_utilities_tab_id = f'ToolsTab'
design_utilities_tab_name = f'UTILITIES'

# Panels
react_demo_panel_name = 'ProParams'
react_demo_panel_id = f'{ADDIN_NAME}'
react_demo_panel_after = 'SolidScriptsAddinsPanel'

# Palettes
parameter_table_palette_name = 'ProParams'
parameter_table_palette_id = f'{ADDIN_NAME}_parameter_table_palette_id '

# Reference for use in some commands
all_workspace_names = [
  'FusionSolidEnvironment', 'GenerativeEnvironment', 'PCBEnvironment', 'PCB3DEnvironment', 'Package3DEnvironment',
  'FusionRenderEnvironment', 'Publisher3DEnvironment', 'SimulationEnvironment', 'CAMEnvironment', 'DebugEnvironment',
  'FusionDocumentationEnvironment', 'ElectronEmptyLbrEnvironment', 'ElectronDeviceEnvironment',
  'ElectronFootprintEnvironment', 'ElectronSymbolEnvironment', 'ElectronPackageEnvironment'
]
