# Shared settings for the Script Runner add-in.

# Debug logging goes to Fusion's Text Command window while developing.
DEBUG = True

ADDIN_NAME = 'ScriptRunner'
COMPANY_NAME = 'ConnorE'

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Shared CHE panel on the Design Solid tab, inserted after Assemble.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
