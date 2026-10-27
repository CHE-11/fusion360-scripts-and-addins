import os

# When True, log messages are also written to the Text Commands window.
DEBUG = False

ADDIN_NAME = 'RestartAddIns'
COMPANY_NAME = 'CHE'

# Must match the id in RestartAddIns.manifest.
ADDIN_ID = 'c4e8a1d7-6b25-4f90-9c3e-2d7a5b8e1f04'
ADDIN_FOLDER = os.path.dirname(os.path.abspath(__file__))

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Shared CHE panel on the Design Solid tab, inserted after Assemble.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
