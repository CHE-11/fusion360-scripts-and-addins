# Shared settings for the Threader add-in.

# Debug logging goes to Fusion's Text Command window while developing.
DEBUG = True

# When True, the palette loads the Vite dev server instead of the built HTML.
# Leave this False so the add-in works without a dev server running.
REACT_DEV = False

ADDIN_NAME = 'Threader'
COMPANY_NAME = 'CHE'

PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_palette'
DEV_PALETTE_URL = 'http://localhost:5174/'

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Shared CHE panel, inserted after the named panel.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
