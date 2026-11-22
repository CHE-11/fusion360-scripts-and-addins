import os

# When True, log messages are also written to the Text Commands window.
DEBUG = False

ADDIN_NAME = 'ExportCutSheet'
COMPANY_NAME = 'CHE'

# Must match the id in ExportCutSheet.manifest.
ADDIN_ID = '32059797-fa7e-4218-a391-7381436580b3'
ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))

WORKSPACE_ID = 'FusionSolidEnvironment'

# Shared CHE panel on the Design Solid tab, inserted after Assemble.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TAB_ID = 'SolidTab'
RIBBON_PANEL_ID = 'CHE_SolidPanel'
RIBBON_AFTER_PANEL_ID = 'SolidAssemblePanel'
