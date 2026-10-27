# Shared settings for the CONstrainer add-in.

# Debug logging goes to Fusion's Text Command window while developing.
DEBUG = True

# When True, the palette loads the Vite dev server instead of the built HTML.
# Leave this False so the add-in works without a dev server running.
REACT_DEV = False

ADDIN_NAME = 'CONstrainer'
COMPANY_NAME = 'ConnorE'

PALETTE_ID = f'{COMPANY_NAME}_{ADDIN_NAME}_palette'
DEV_PALETTE_URL = 'http://localhost:5173/'

WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_ID = 'SolidScriptsAddinsPanel'
COMMAND_BESIDE_ID = 'ScriptsManagerCommand'

# Shared CHE panels, inserted after the named panel.
# SketchTab is contextual and shows while a sketch is being edited.
RIBBON_PANEL_NAME = 'CHE'
RIBBON_TABS = (
    ('SketchTab', 'CHE_SketchPanel', 'SketchConstraintsPanel'),
    ('SolidTab', 'CHE_SolidPanel', 'SolidAssemblePanel'),
)
