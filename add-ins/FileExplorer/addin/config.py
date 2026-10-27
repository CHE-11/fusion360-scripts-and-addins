# Shared settings for the File Explorer add-in.

# Debug logging goes to Fusion's Text Command window while developing.
DEBUG = True

# When True, the palette loads the Vite dev server instead of the built HTML.
# Leave this False so the add-in works without a dev server running.
REACT_DEV = False

ADDIN_NAME = 'FileExplorer'
COMPANY_NAME = 'CHE'

PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_palette'
DEV_PALETTE_URL = 'http://localhost:5176/'

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Shared CHE panel on the Design Solid tab, inserted after Assemble.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
