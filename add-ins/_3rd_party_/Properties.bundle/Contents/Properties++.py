#Author-KleiTools
#Description-Evaluatin version of Properties++. Properties ++ is an add-in for Fusion 360 which aims to help you at managing your data. This data management is based on adding custom properties to your components and designs. When your design is done you could easily export your custom data as if it were part of a Bill of Materials. 

# Software om eigen eigenschappen toe te kennen aan componenten
# Maak eigenschappen aan in de Manager
#   Eigenschappen worden ingedeeld in 4 Categorieën, componenten, samenstellingen en designs. Plus een algemene categorie doe altijd zichtbaar is
#   Deze lijst met eigenschappen wordt opgeslagen in het rootComponent mbv aan attribuut
#       Attributengroep is PropertiesPP, tabellen zijn CustProp_0 (Componenten) t/m CustProp_3 (Algemeen)
#       Rijen van tabel bevat één lange strings met alle eigenschappen die bij deze categorie horen. Verdeling van eingeschap gesplitst mbv '~~'
#       Opnieuw onderverdeel in individuele eigenschappen van eigenschap, gescheiden met '~'. Onderverdeling in uniek ID, type (text of integer enz) en benaming
#       Voorbeeld van string: 'id_eigenschap1~type_eigenschap_1~naam_eigenschap1~~id_eigenschap2~type_eigenschap_2~naam_eigenschap2~~'
# Nadat de manager is ingevuld zijn deze unieke eigenschappen per component in te stellen.
#   Stel per component in wat de juiste stijl is ( comp, samenstelling, design). Als deze nog niet is ingesteld wordt deze automatisch ingeschat
#   Ingevulde informatie wordt opgeslagen in attributen van het component. Er wordt een nieuwe attribute aangemaakt per bestaande eigenschap
#       Attribute: Groep is PropertiesPP, Tabel is gelijk aan het id van de eigenschap (zoals gedifinieerd in eigenschappen rootComponent), waarde is de ingevulde waarde van gebruiker

import adsk.core, adsk.fusion, traceback, time, webbrowser, csv, os, locale
from pathlib import Path

_app = adsk.core.Application.get()
_ui  = _app.userInterface
_rowNumber = 0

#Publieke parameters
_vorigeSelectie = ''

# Instellingen
verbergErrors = True
trial = False
teller = None               # teller voor Trial versie
trialBericht = 25           # Geef een melding wanneer de trial boven dit getal is
trialStartwaarde = -25      # Eerste keer gebruik app duurt het wat langer voordat de meldingen beginnen
versie = 1                  # Versienummer om bij te ouden om welke versie van het product het gaat

# Global set of event handlers to keep them referenced for the duration of the command
_handlers = []
cmdDefsR = []
entities = []
_rowNumber = 0

app = adsk.core.Application.get()
materialsMap = {}
Component = ""

def run(context):
    try:

        # Voeg Manager-knop toe aan een aantal verschillende panelen
        cmdDefs = _ui.commandDefinitions
        if cmdDefs.itemById('idPPPSnelmenu') is None:
            PPPSnelmenuKnop = cmdDefs.addButtonDefinition('idPPPSnelmenu', 'Manage Properties','Manage all available custom properties for Properties++', './Resources/Manage')
            panels = ['SolidModifyPanel', 'SheetMetalModifyPanel', 'AssembleModifyPanel', 'SurfaceModifyPanel', 'PCBModifyPanel', 'ManagePanel', 'SolidScriptsAddinsPanel']
            for n in range(len(panels)):
                panel = _ui.allToolbarPanels.itemById(panels[n])
                if panel is not None:
                    panel.controls.addSeparator()
                    panel.controls.addCommand(PPPSnelmenuKnop)
        else:
            PPPSnelmenuKnop = cmdDefs.itemById('idPPPSnelmenu')
        knopPPPManager = uiManager()
        PPPSnelmenuKnop.commandCreated.add(knopPPPManager)
        _handlers.append(knopPPPManager)


        #knop in contextmenu
        def setLinearMarkingMenu(args):
            linearMenu = adsk.core.MarkingMenuEventArgs.cast(args).linearMarkingMenu
            #linearMenu.clear()
            if args.selectedEntities:
                sel0 = args.selectedEntities[0]
                componentChk = adsk.fusion.Component.cast(sel0)
                occurenceChk = adsk.fusion.Occurrence.cast(sel0)
                # Knop alleen beschikbaar als het component of occurence is
                if componentChk or occurenceChk:
                    #Knop alleen beschikbaar als het de juiste werkomgeving aan staat
                    workspace = str(adsk.core.Application.get().userInterface.activeWorkspace.id)
                    if workspace == 'FusionRenderEnvironment' or workspace == 'FusionSolidEnvironment':
                        cmdDefSpecial = _ui.commandDefinitions.itemById('idPPPContextmenu')
                        linearMenu.controls.addSeparator()
                        linearMenu.controls.addCommand(cmdDefSpecial)
        class MyMarkingMenuHandler(adsk.core.MarkingMenuEventHandler):
            def notify(self, args):
                    setLinearMarkingMenu(args)
        # Add customized handler for marking menu displaying
        onMarkingMenuDisplaying = MyMarkingMenuHandler()
        _handlers.append(onMarkingMenuDisplaying)
        _ui.markingMenuDisplaying.add(onMarkingMenuDisplaying)
        # Create special command for brep entities
        cmdDefPPPContext = _ui.commandDefinitions.itemById('idPPPContextmenu')
        if not cmdDefPPPContext:
            cmdDefPPPContext = _ui.commandDefinitions.addButtonDefinition('idPPPContextmenu', 'Properties++', 'Manage your design data by adding custom properties.', './Resources/P')
            cmdDefsR.append(cmdDefPPPContext)
        KnopContextAangemaakt = MyCommandCreatedHandler()
        cmdDefPPPContext.commandCreated.add(KnopContextAangemaakt)
        _handlers.append(KnopContextAangemaakt)
        
        # trial invullen
        if trial == True and teller is None:
            trialStart()

    except:
        if _ui:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))


# Event handler that reacts when the command definitio is executed which
# results in the command being created and this event being fired.
class MyCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _handlers
            
            # Trial teller
            trialGebruik()
            
            # Get the command that was created.
            cmd = adsk.core.Command.cast(args.command)
            inputs = cmd.commandInputs
            
            # Controleer of standaard eigenschappen moeten worden toegevoegd
            useStandard(inputs)

            #Standaarden instellen
            #cmd.okButtonText = 'Save'
            cmd.isRepeatable = False        # Had wel gemogen maar door een fout in customPropPlaatsen kan die functie niet verplaatst worden naar het moment dat er pas geselecteerd wordt. Zie notitie in customPropPlaatsen()
            cmd.helpFile = 'help.pdf'

            # Connect to the input changed event.
            onInputChanged = MyCommandInputChangedHandler()
            cmd.inputChanged.add(onInputChanged)
            
            _handlers.append(onInputChanged)

            # Selectiefilter toevoegen
            selectionInput = inputs.addSelectionInput('idSelect', 'Component', 'Select Component or Assembly')
            selectionInput.setSelectionLimits(1,1)
            selectionInput.addSelectionFilter('Occurrences')
            selectionInput.addSelectionFilter('RootComponents')

            #Berichten voor gelinked model toevoegen
            message = '<div align="center"><i>Note: Linked components are read-only.</i></div>'
            txtLinked = inputs.addTextBoxCommandInput('idTxtLinked', '', message, 1, True)
            BtnOpen = inputs.addBoolValueInput('idBtnOpen', 'Open file', False, 'resources/open', True)
            txtLinked.isVisible = False
            BtnOpen.isVisible = False
            BtnOpen.tooltip = 'Open de selected component to make any changes'
            
            #Bericht voor niet opgeslagen modellen
            messageSave = '<div align="center"><font color="red"><i>Note: Save document before editing properties!</i></font></div>'
            txtSaveReminder = inputs.addTextBoxCommandInput('idTxtSaveReminder', '', messageSave, 1, True)
            txtSaveReminder.isVisible = False
            
            #Standaard informatie
            NumberInput = inputs.addStringValueInput('idNumberInput', 'Part Number', '')
            NameInput = inputs.addStringValueInput('idNameInput', 'Part Name', '')
            DescriptionInput = inputs.addStringValueInput('idDescriptionInput', 'Description', '')
            NumberInput.isEnabled = False
            NameInput.isEnabled = False
            DescriptionInput.isEnabled = False

            # Create group input.
            GroepFisiek = inputs.addGroupCommandInput('idGroepFisiek', 'Physical properties')
            GroepFisiek.isEnabledCheckBoxDisplayed = False
            groepFisiekInput = GroepFisiek.children

            # textboxes
            AreaInput = groepFisiekInput.addTextBoxCommandInput('idAreaInput', 'Area', '', 1, True)
            GewichtInput = groepFisiekInput.addTextBoxCommandInput('idGewichtInput', 'Mass', '', 1, True)
            VolumeInput = groepFisiekInput.addTextBoxCommandInput('idVolumeInput', 'Volume', '', 1, True)
            AreaInput.isEnabled = False
            GewichtInput.isEnabled = False
            VolumeInput.isEnabled = False

            # Materiaal dropdown
            dropdownMatInput = groepFisiekInput.addDropDownCommandInput('idMatInput', 'Material', adsk.core.DropDownStyles.TextListDropDownStyle);
            materialLibNames = getMaterialLibNames()
            materials = getMaterialsFromLib(materialLibNames[0], '')
            listItems = dropdownMatInput.listItems
            for materialName in materials :
                listItems.add(materialName, False, '')
            dropdownMatInput.isEnabled = False

            # Verborgen tekstvak indien Materiaal niet uitgelezen kan worden
            idMatError = groepFisiekInput.addTextBoxCommandInput('idMatError', 'Material', ' < not available >', 1, True)
            idMatError.isVisible = False

            # Groep voor custom properties
            GroepCustProp = inputs.addGroupCommandInput('idGroepCustProp', 'Custom Properties')
            #GroepCustProp.isFullWidth = True
            GroepCustProp.isEnabledCheckBoxDisplayed = False
            GroepCustProp.isExpanded = True
            groepCustPropInput = GroepCustProp.children

            # Dropdown voor properties stijl
            PropStijl = groepCustPropInput.addDropDownCommandInput('idPropStijl', 'Style', adsk.core.DropDownStyles.LabeledIconDropDownStyle);
            PropStijlItems = PropStijl.listItems
            PropStijlItems.add('Part', False, 'resources/Component')
            PropStijlItems.add('Assembly', False, 'resources/Assembly')
            PropStijlItems.add('Design', False, 'resources/RootComponent')
            PropStijl.isEnabled = False
            PropStijl.tooltip = 'Property style of component'
            PropStijl.tooltipDescription = "Each component can have a different property style. Depending on the selected style different properties will be shown. The style therefore functions as a filter to only show properties that apply to this component. \n\nWhen the style has not yet been set, Properties++ will try to estimate what style should be used. Once the properties have been saved, so will the selected style. You wil always be able to switch styles at a later time. \n\nCreate or remove properties using the 'Manage Properties' function in the MODIFY panel. The 'common properties' will be shown independend of the selected style."

             # plaats custom properties. Alle eigenschappen worden geplaatst, onafhankelijk van het filter.
            customPropPlaatsen(groepCustPropInput, inputs)

            # Wat gebeurd er als je op OK drukt?
            # Get the command
            cmd2 = adsk.core.CommandCreatedEventArgs.cast(args).command
            onExecute = OkKnop()
            cmd2.execute.add(onExecute)
            
            _handlers.append(onExecute)
            
            # deel argumenten voor later
            global GedeeldeArgumenten
            GedeeldeArgumenten = cmd

        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

def ouderDoc():
    
    # Afhankelijk van wat het bovenliggende model is moet worden bepaald waar de eigenschappen staan
    # Van belang bij het selecteren van het rootComponent, deze is anders voor gelinkte modellen
    # Onderaan ook controle van het juiste type selectie 
    design = adsk.core.Application.get().activeProduct
    ui = adsk.core.Application.get().userInterface
    if ui.activeSelections.count > 0:
        selectie = ui.activeSelections.item(0).entity
        global _vorigeSelectie
        _vorigeSelectie = selectie
    else:
        selectie = _vorigeSelectie
    ouder = design.rootComponent

    if selectie.objectType != 'adsk::fusion::Component' and selectie.objectType == 'adsk::fusion::Occurrence':
        if design != selectie.component.parentDesign:
            ouder = selectie.component.parentDesign.rootComponent
    # Verbreek selectie als het van het verkeerde bestandsformaat is!   
    elif selectie.objectType != 'adsk::fusion::Component' and selectie.objectType != 'adsk::fusion::Occurrence':
        ui.activeSelections.clear()
    return ouder

def customPropPlaatsen(groepCustPropInput, inputs):
# deze functie plaatst de menuitems van de custom properties.
# De functie wordt aangeroepen tijdens het opbouwen van het menu zodat de eventArgs goed doorkomen, als je dat niet doet en je drukt op een knop die hieronder wordt aangemaakt wordt dat niet herkend door de InputChangedHandler. 
# Bovenstaand kan aarschijnlijk verbeterd worden. Door huidige opbouw kan het commando niet goed herhaald worden. 
        try:
                    
            design = adsk.core.Application.get().activeProduct
            for n in range(4):
                attribuutGroep = 'custProp_' + str(n)
    
                ouder = ouderDoc()
                attr = ouder.attributes.itemByName('ProppertiesPP', attribuutGroep)
                if attr is not None:
                    tekst = attr.value
                    #_ui.messageBox(tekst)
                    if tekst != ' ':
                        regel = tekst.split('~~')
                        for i in range(len(regel)-1):
                            param = regel[i]
                            param = param.split('~')
                            gId = 'CP_' + param[0]          #Niet uniek, ieder onderdeel krijgt nu dezelfde.
                            gIdCurrency = gId + 'Currency'
                            gIdLink = gId + '_Link'
                            typePara = param[1]
                            naam = param[2]
                            if typePara == 'Text': groepCustPropInput.addStringValueInput(gId, naam)
                            elif typePara == 'Integer': groepCustPropInput.addIntegerSpinnerCommandInput(gId, naam, -2147483647, 2147483647, 1, 0)
                            elif typePara == 'Number': groepCustPropInput.addFloatSpinnerCommandInput(gId, naam, '', -2147483647, 2147483647, 1, 0)
                            elif typePara == 'Currency':
                                groepCustPropInput.addFloatSpinnerCommandInput(gId, naam, '', 0, 2147483647, 1, 0)
                                eenheid = groepCustPropInput.addDropDownCommandInput(gIdCurrency, ' ' , 1)
                                munteenheid = currencyList()
                                for x in range( len(munteenheid)):
                                    munteenheidPrint = str(munteenheid[x][0]) #+ ' - ' + str(munteenheid[x][1])
                                    instellingenString = ouder.attributes.itemByName('ProppertiesPP', 'Instellingen').value
                                    munteenheidIndex = int(instellingenString.split('~')[0])
                                    if x == munteenheidIndex:
                                        eenheid.listItems.add(munteenheidPrint, True)
                                    else:
                                        eenheid.listItems.add(munteenheidPrint, False)
                            elif typePara == 'URL':
                                groepCustPropInput.addStringValueInput(gId, naam)
                                knopLink = groepCustPropInput.addBoolValueInput(gIdLink, ' ', False)
                                knopLink.text = 'Follow Link'
                            elif typePara == 'Yes/No': groepCustPropInput.addBoolValueInput(gId, naam, True)
                            elif typePara == 'Multiline text': groepCustPropInput.addTextBoxCommandInput(gId, naam, '', 2, False)
    
                            #inactief in geval van link
                            if ouder != design.rootComponent: #dus link
                                inputs.itemById(gId).isEnabled = False
                                try:
                                    gId += 'Currency'
                                    inputs.itemById(gId).isEnabled = False
                                except:
                                    continue
        except:
            errorReport('fout:\n{}'.format(traceback.format_exc()))

def currencyList():
    currency_list = (
        ('ALL', 'Albania Lek'),
        ('AFN', 'Afghanistan Afghani'),
        ('ARS', 'Argentina Peso'),
        ('AWG', 'Aruba Guilder'),
        ('AUD', 'Australia Dollar'),
        ('AZN', 'Azerbaijan New Manat'),
        ('BSD', 'Bahamas Dollar'),
        ('BBD', 'Barbados Dollar'),
        ('BDT', 'Bangladeshi taka'),
        ('BYR', 'Belarus Ruble'),
        ('BZD', 'Belize Dollar'),
        ('BMD', 'Bermuda Dollar'),
        ('BOB', 'Bolivia Boliviano'),
        ('BAM', 'Bosnia and Herzegovina Convertible Marka'),
        ('BWP', 'Botswana Pula'),
        ('BGN', 'Bulgaria Lev'),
        ('BRL', 'Brazil Real'),
        ('BND', 'Brunei Darussalam Dollar'),
        ('KHR', 'Cambodia Riel'),
        ('CAD', 'Canada Dollar'),
        ('KYD', 'Cayman Islands Dollar'),
        ('CLP', 'Chile Peso'),
        ('CNY', 'China Yuan Renminbi'),
        ('COP', 'Colombia Peso'),
        ('CRC', 'Costa Rica Colon'),
        ('HRK', 'Croatia Kuna'),
        ('CUP', 'Cuba Peso'),
        ('CZK', 'Czech Republic Koruna'),
        ('DKK', 'Denmark Krone'),
        ('DOP', 'Dominican Republic Peso'),
        ('XCD', 'East Caribbean Dollar'),
        ('EGP', 'Egypt Pound'),
        ('SVC', 'El Salvador Colon'),
        ('EEK', 'Estonia Kroon'),
        ('EUR', 'Euro Member Countries'),
        ('FKP', 'Falkland Islands (Malvinas) Pound'),
        ('FJD', 'Fiji Dollar'),
        ('GHC', 'Ghana Cedis'),
        ('GIP', 'Gibraltar Pound'),
        ('GTQ', 'Guatemala Quetzal'),
        ('GGP', 'Guernsey Pound'),
        ('GYD', 'Guyana Dollar'),
        ('HNL', 'Honduras Lempira'),
        ('HKD', 'Hong Kong Dollar'),
        ('HUF', 'Hungary Forint'),
        ('ISK', 'Iceland Krona'),
        ('INR', 'India Rupee'),
        ('IDR', 'Indonesia Rupiah'),
        ('IRR', 'Iran Rial'),
        ('IMP', 'Isle of Man Pound'),
        ('ILS', 'Israel Shekel'),
        ('JMD', 'Jamaica Dollar'),
        ('JPY', 'Japan Yen'),
        ('JEP', 'Jersey Pound'),
        ('KZT', 'Kazakhstan Tenge'),
        ('KPW', 'Korea (North) Won'),
        ('KRW', 'Korea (South) Won'),
        ('KGS', 'Kyrgyzstan Som'),
        ('LAK', 'Laos Kip'),
        ('LVL', 'Latvia Lat'),
        ('LBP', 'Lebanon Pound'),
        ('LRD', 'Liberia Dollar'),
        ('LTL', 'Lithuania Litas'),
        ('MKD', 'Macedonia Denar'),
        ('MYR', 'Malaysia Ringgit'),
        ('MUR', 'Mauritius Rupee'),
        ('MXN', 'Mexico Peso'),
        ('MNT', 'Mongolia Tughrik'),
        ('MZN', 'Mozambique Metical'),
        ('NAD', 'Namibia Dollar'),
        ('NPR', 'Nepal Rupee'),
        ('ANG', 'Netherlands Antilles Guilder'),
        ('NZD', 'New Zealand Dollar'),
        ('NIO', 'Nicaragua Cordoba'),
        ('NGN', 'Nigeria Naira'),
        ('NOK', 'Norway Krone'),
        ('OMR', 'Oman Rial'),
        ('PKR', 'Pakistan Rupee'),
        ('PAB', 'Panama Balboa'),
        ('PYG', 'Paraguay Guarani'),
        ('PEN', 'Peru Nuevo Sol'),
        ('PHP', 'Philippines Peso'),
        ('PLN', 'Poland Zloty'),
        ('QAR', 'Qatar Riyal'),
        ('RON', 'Romania New Leu'),
        ('RUB', 'Russia Ruble'),
        ('SHP', 'Saint Helena Pound'),
        ('SAR', 'Saudi Arabia Riyal'),
        ('RSD', 'Serbia Dinar'),
        ('SCR', 'Seychelles Rupee'),
        ('SGD', 'Singapore Dollar'),
        ('SBD', 'Solomon Islands Dollar'),
        ('SOS', 'Somalia Shilling'),
        ('ZAR', 'South Africa Rand'),
        ('LKR', 'Sri Lanka Rupee'),
        ('SEK', 'Sweden Krona'),
        ('CHF', 'Switzerland Franc'),
        ('SRD', 'Suriname Dollar'),
        ('SYP', 'Syria Pound'),
        ('TWD', 'Taiwan New Dollar'),
        ('THB', 'Thailand Baht'),
        ('TTD', 'Trinidad and Tobago Dollar'),
        ('TRY', 'Turkey Lira'),
        ('TRL', 'Turkey Lira'),
        ('TVD', 'Tuvalu Dollar'),
        ('UAH', 'Ukraine Hryvna'),
        ('GBP', 'United Kingdom Pound'),
        ('USD', 'United States Dollar'),
        ('UYU', 'Uruguay Peso'),
        ('UZS', 'Uzbekistan Som'),
        ('VEF', 'Venezuela Bolivar'),
        ('VND', 'Viet Nam Dong'),
        ('YER', 'Yemen Rial'),
        ('ZWD', 'Zimbabwe Dollar')
    )

    return(sorted(currency_list))


# Gebruikersvenster voor Properties++ Manager
class uiManager(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            global _handlers
            
            # Trial teller
            trialGebruik()
            
            # Get the command that was created.
            cmd = adsk.core.Command.cast(args.command)
            inputs = cmd.commandInputs
            
            # Controleer of de standaard ingevuld moet worden
            useStandard(inputs)

            # Connect to the input changed event.
            onInputChanged = ManagerInputChanged()
            cmd.inputChanged.add(onInputChanged)
            _handlers.append(onInputChanged)

            # Create tab input
            tabComp = inputs.addTabCommandInput('idManageTab_0', 'Part properties', 'resources/Component' )
            #tabSubComp = tabComp.children
            tabComp._set_tooltipDescription('Manage custom properties for all components marked as Part.')
            tabAssy = inputs.addTabCommandInput('idManageTab_1', 'Assembly properties', 'resources/Assembly')
            #tabSubAssy = tabAssy.children
            tabAssy._set_tooltipDescription('Manage custom properties for all components marked as Assembly.')
            tabDesign = inputs.addTabCommandInput('idManageTab_2', 'Design properties', 'resources/RootComponent')
            #tabSubDesign = tabDesign.children
            tabDesign._set_tooltipDescription('Manage custom properties for all components marked as Design. (The Design style is most commonly the RootComponent.)')
            tabGeneric = inputs.addTabCommandInput('idManageTab_3', 'Common properties', 'resources/Subset')
            #tabSubGeneric = tabGeneric.children
            tabGeneric._set_tooltipDescription('Manage custom properties which will be common to all components, independant of their style.')
            tabSettings = inputs.addTabCommandInput('idManageTab_4', 'Options', 'resources/Settings' )
            tabSubSettings = tabSettings.children


            # Voeg tabellen toe aan verschillende tabbladen
            for each in range(4):
                tabId = 'idManageTab_' + str(each)
                tab = inputs.itemById(tabId).children
                tabNaam = inputs.itemById(tabId).name
                tabelId = 'idTabel_' + str(each)
                tabelNaam = 'tabel' + tabNaam
                plusKnopId = 'idPlus_' + str(each)
                delKnopId = 'idDel_' + str(each)
                omhoogKnopId = 'idUp_' + str(each)
                omlaagKnopId = 'idDown_' + str(each)

                # Create table input
                tab.addTableCommandInput(tabelId, tabelNaam, 2, '1:1')
                tabel = inputs.itemById(tabelId)
                tabel.maximumVisibleRows = 10
                tabel.minimumVisibleRows = 3

                # Add inputs into the table.
                add = tab.addBoolValueInput(plusKnopId, 'Add', False, 'resources/plus', True)
                dell = tab.addBoolValueInput(delKnopId, 'Delete', False, 'resources/x', True)
                up = tab.addBoolValueInput(omhoogKnopId, 'Upp', False, 'resources/Up', True)
                down = tab.addBoolValueInput(omlaagKnopId, 'Down', False, 'resources/Down', True)
                tabel.addToolbarCommandInput(add)
                tabel.addToolbarCommandInput(dell)
                tabel.addToolbarCommandInput(up)
                tabel.addToolbarCommandInput(down)
                add.tooltip = 'Add a new property.'
                dell.tooltip = 'Delete the selected property.'
                up.tooltip = 'Move the selected property up to change the order of presentation.'
                down.tooltip = 'Move the selected property down to change the order of presentation.'


            # Instelling standaard munteenheid
            muntlijst = tabSubSettings.addDropDownCommandInput('idSetMunt', 'Default Currency' , 1)
            munteenheid = currencyList()
            for x in range(len(munteenheid)):
                munteenheidPrint = str(munteenheid[x][0]) + ' - ' + str(munteenheid[x][1])
                muntlijst.listItems.add(munteenheidPrint, False)
            muntlijst.tooltip = "Default currency for 'Currency' properties"
            muntlijst.tooltipDescription = "For each component that has a 'Currency' property you will be able to select a different currency. However, when this is not yet set, the selected currency will be equal to the Default Currency."

            # Knoppen voor Template opslaan of inladen
            templateKnop = tabSubSettings.addButtonRowCommandInput('idTemplateKnoppen', 'Template', True)
            exportKnop = templateKnop.listItems.add('Export properties as template', False, 'resources/templateExport')            
            importKnop = templateKnop.listItems.add('Import properties from template', False, 'resources/templateImport')            
            exportKnop.tooltip = 'Export properties as template'
            importKnop.tooltip = 'Import properties from template'
            importKnop._set_tooltipDescription = "To reuse the same set of properties in different files; export the current setup as template, then import the same template in your second file. \n\nIt is considered good practise to create one or multiple templates which can be used for various designs. This will ensure a faster workflow and more consistant data structures."
            exportKnop._set_tooltipDescription = "To reuse the same set of properties in different files; export the current setup as template, then import the same template in your second file. \n\nIt is considered good practise to create one or multiple templates which can be used for various designs. This will ensure a faster workflow and more consistant data structures."

            # Standard knop
            standardKnop = tabSubSettings.addBoolValueInput('idExportStandard', 'Make Standard', False, 'resources/standardExport')
            standardKnop.tooltip = 'Make these custom properties the standard'
            standardKnop.tooltipDescription = 'Save current set of properties as the standard. All new files will open with this set of custom properties.'
            if trial == True:
                standardKnop.isEnabled = False
                standardKnop.tooltip = standardKnop.tooltip + ' (Full version only)'
                standardKnop.tooltipDescription = standardKnop.tooltipDescription + '\n\n This function is not available for the evaluation version (Trial) of Properties++'

            # Export knop
            exportCSV = tabSubSettings.addBoolValueInput('idExportCSV', 'Export data/BOM', False, 'resources/csvExport' )
            exportCSV.tooltip = 'Export data as Bill Of Materials'
            exportCSV.tooltipDescription = 'Export a table of all components, their quantities and custom properties. \n\nThe table will be saved in CSV-format and can be opened by any major spreadsheet editing software, such as Microsoft Excel, Google Spreadsheet and Apple Numbers.'

            # Controleer of er al parameters bestaan
            ManagerOnLoad(args, None)

            # Instellingen venster
            cmd.helpFile = 'help.pdf'
            cmd.isRepeatable = True

            # Wat gebeurd er als je op OK drukt?
            cmd2 = adsk.core.CommandCreatedEventArgs.cast(args).command
            onExecute = OkKnopManager()
            cmd2.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

class ManagerInputChanged(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            ui = adsk.core.Application.get().userInterface
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            inputs = eventArgs.inputs

            # Parameters voorbereiden
            try:
                eventId = eventArgs.input.id.split('_')[0]
                eventIdNum = eventArgs.input.id.split('_')[1]
                tabelId = 'idTabel_' + str(eventIdNum)
                tableInput = inputs.itemById(tabelId)
            except:
                eventId = eventArgs.input.id

            #Voeg rij toe of verwijder rij
            if eventId == 'idPlus':
                addRowToTable(tableInput, '', '', '')
            elif eventId == 'idDel':
                if tableInput.selectedRow == -1:
                    #Wat als er geen rij is geselecteerd
                    ui.messageBox('Please select a row to delete')
                else:
                    # Controleer of dit een parameter is die voorheen al bestond. Geef in dat geval een waarschuwing.
                    if tableInput.getInputAtPosition(tableInput.selectedRow,1).isEnabled == False:
                        controle = _ui.messageBox('Removing a propertie which is already used in your design might result in loss of information. Are you sure you would like to continue?', 'Properties++', 1, 2)
                        if controle == False:
                            tableInput.deleteRow(tableInput.selectedRow)
                    else:
                        tableInput.deleteRow(tableInput.selectedRow)

            elif eventId == 'idUp':
                volgordeRijdenManager('Omhoog', tableInput)
            elif eventId == 'idDown':
                volgordeRijdenManager('Omlaag', tableInput)

            elif eventId == 'idTemplateKnoppen':
                # controleer wele knop is ingedrukt
                knoppenRijItems = inputs.itemById('idTemplateKnoppen').listItems
                for k in range(knoppenRijItems.count):
                    if knoppenRijItems.item(k).isSelected == True:
                        knop = k
                        # Zet selectie weer uit
                        knoppenRijItems.item(k).isSelected = False
                # Geef aan wat er moet gebeuren op basis van knop
                if knop == 0:
                    exportTemplate(inputs, True)
                elif knop == 1:
                    importTemplate(inputs, True)
                    
            elif eventId == 'idExportStandard':
                vraag = _ui.messageBox('Are you sure you would like to save the current property set as the standard? Doing so will result in all new designs to use these same custom properties. \n\nYou will always be able to change the custom properties or the standard.' , 'Properties++', 4)
                if vraag == 2:
                    exportTemplate(inputs, False)

            elif eventId == 'idExportCSV':
                exportCSV()

        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

def importTemplate(inputs, locatieSelecteerbaar):
    try:
         # Definitie aanpassen
        inputs = inputs.command.commandInputs
        
        # Definiëer
        design = adsk.core.Application.get().activeProduct

        # Maak bestand aan
        if locatieSelecteerbaar == True:
            dialoogBox  = _ui.createFileDialog()
            dialoogBox.isMultiSelectEnabled = False
            dialoogBox.title = 'Import template for Properties++'
            dialoogBox.filter = 'Properties++ template (*.Pppt)'
            if dialoogBox.showOpen() != adsk.core.DialogResults.DialogOK:
                return
            bestandsnaam = dialoogBox.filename
        else:
            bestandsnaam = bestandLocatie('standard').replace(".txt",".PppS")

        # Open bestand, lees bestand
        with open(bestandsnaam, "r") as ins:
            inhoud = []
            for regel in ins:
                regel = regel.strip('\n')
                inhoud.append(regel)

        # Schrijf instellingen naar attributen van root
        for i in range(5):
            if i != 4:
                attribuutGroep = 'custProp_' + str(i)
            else:
                attribuutGroep = 'Instellingen'
            design.rootComponent.attributes.add('ProppertiesPP', attribuutGroep, inhoud[i])

        # Verwijder eventueel huidige tabelrijen
        if locatieSelecteerbaar == True:
            if locatieSelecteerbaar == True:
                verwijderHuidig = _ui.messageBox('Replace current property set? This will remove all properties that are currently set up.' , 'Properties++', 4)
            else:
                verwijderHuidig = 2
            if verwijderHuidig == 2:
                #Leeg tabellen
                for i in range(4):
                    tabelId = 'idTabel_' + str(i)
                    if inputs.itemById(tabelId) is not None:
                        inputs.itemById(tabelId).clear()
            elif verwijderHuidig == 1:
                return

            #Schrijf rijen van tabellen
            ManagerOnLoad(None, inputs)

    except:
        _ui.messageBox('There has been an error importing your template. Please check the template file.')
        errorReport('Failed:\n{}'.format(traceback.format_exc()))



def exportTemplate(inputs, locatieSelecteerbaar):
    try:
        # Definite aanpassen
        inputs = inputs.command.commandInputs       #ontsnap aan de inputs van alleen dit tabblad. Zoek naar inputs van hele commando

        # Schrijf manager data weg
        design = adsk.core.Application.get().activeProduct
        propertiesOpslaan(inputs, design)

        # Definiëer
        design = adsk.core.Application.get().activeProduct

        # Maak bestand aan
        if locatieSelecteerbaar == True:
            dialoogBox  = _ui.createFileDialog()
            dialoogBox.title = 'Export template for Properties++'
            dialoogBox.filter = 'Properties++ template (*.Pppt)'
            if dialoogBox.showSave() != adsk.core.DialogResults.DialogOK :
                return
            bestandsnaam = dialoogBox.filename
        else:
            bestandsnaam = bestandLocatie('standard').replace(".txt",".PppS")

        try:
            test = open(bestandsnaam, 'w')
            test.close()
        except:
            _ui.messageBox('File could not be saved. Please make sure the file has not been opened in another program.')
            return

        # Open bestand
        tem = open(bestandsnaam,"w")

        # Schrijf eigenschappen
        for i in range(4):
            attribuutGroep = 'custProp_' + str(i)
            Eigenschap = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
            if Eigenschap is not None:
                regel = Eigenschap.value
            else:
                regel = ''
            tem.write(regel + '\n')

        # Schrijf instelligen
        Eigenschap = design.rootComponent.attributes.itemByName('ProppertiesPP', 'Instellingen')
        if Eigenschap is not None:
            regel = Eigenschap.value + '\n'
        else:
            regel = '\n'
        tem.write(regel)

        # sluit het bestand
        tem.close()

        _ui.messageBox('File succesfully saved.')

    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))

def useStandard(inputs):
    # Definiëer
    design = adsk.core.Application.get().activeProduct        
    # Controleer of er al custom properties aanwezig zijn
    if design.rootComponent.attributes.itemByName('ProppertiesPP', 'custProp_0') is None:
        bestandsnaam = bestandLocatie('standard').replace(".txt",".PppS")
        pad = Path(bestandsnaam)
        # Controleer of het standaard bestand bestaat en of the trial niet aan staat
        if pad.is_file() and trial != True:
            # verander de template informatie
            importTemplate(inputs, False)

def exportCSV():
    # Definiëer
    design = adsk.core.Application.get().activeProduct

    # Maak bestand-dialoog venster
    dlg = _ui.createFileDialog()
    dlg.title = 'Export Data/BOM'
    dlg.filter = 'Comma Separated Values (*.csv);;All Files (*.*)'
    if dlg.showSave() != adsk.core.DialogResults.DialogOK :
        return
    bestandsnaam = dlg.filename

    # Controleer of het bestand niet in gebruik is
    try:
        test = open(bestandsnaam, 'w')
        test.close()
    except:
        _ui.messageBox('Error trying to edit the file. Please make sure it is not opened by any other program.')
        return

    # Maak CSV bestand en vul BOM in
    with open(bestandsnaam, 'w', newline='', encoding='utf-8') as csvfile:
        
        #voor defenitie van scheidignsteken
        #taalLocale = locale.getdefaultlocale()[0]
        locale.setlocale(locale.LC_ALL, '')
        decimaalteken = locale.localeconv()['decimal_point']
        if decimaalteken == ',':
            scheidingsteken  = ';'
        else:
            scheidingsteken = ','
        
        bestand = csv.writer(csvfile, delimiter=scheidingsteken, quotechar='"', quoting=csv.QUOTE_MINIMAL)

        #Maak een string voor project titel rij
        bestand.writerow(['Root file'])
        tekst = ['-', 'Name', 'Number', 'Description', 'Material']
        # Bepaal stijl van rootComponent
        hoofdcompCP = design.rootComponent.attributes.itemByName('ProppertiesPP', 'PropStijl')
        if hoofdcompCP is not None:
            propStijlIndex = design.rootComponent.attributes.itemByName('ProppertiesPP', 'PropStijl').value
        else:
            propStijlIndex = 2
        # Zoek info op die bij stijl hoort
        attribuutGroep = 'custProp_' + str(propStijlIndex)
        attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
        tekst = tekstEigenschapnamenToevoegen(attribuut, tekst, 2)
        # Voeg ook de overige instellingen toe
        attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', 'custProp_3')
        tekst = tekstEigenschapnamenToevoegen(attribuut, tekst, 2)
        #Schrijf regel
        bestand.writerow(tekst)

        # String voor project eigenschappen
        ProjNaam = design.rootComponent.name
        ProjNummer = design.rootComponent.partNumber
        ProjOmschrijving = design.rootComponent.description
        if design.rootComponent.material is not None:
            ProjMateriaal = design.rootComponent.material.name
        else:
            ProjMateriaal = ' '
        tekst = [' ', ProjNaam, ProjNummer, ProjOmschrijving, ProjMateriaal]
        # Custom Properties lezen, maak lijst van id's
        attribuutGroep = 'custProp_' + str(propStijlIndex)
        attrIds = []
        attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
        attrIds = tekstEigenschapnamenToevoegen(attribuut, attrIds, 0)
        attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', 'custProp_3')
        attrIds = tekstEigenschapnamenToevoegen(attribuut, attrIds, 0)
        # Eigenschappen toevoegen aan tekst
        for I in range(len(attrIds)):
            attr = design.rootComponent.attributes.itemByName('ProppertiesPP', attrIds[I])
            if attr is not None:
                attrValue = attr.value
            else:
                attrValue = ''
            tekst.append(attrValue)
        #Schrijf regel
        bestand.writerow(tekst)

       
        # Maak nieuwe tabellen voor alle component-stijlen
        # Definiëer de teksten die later worden weggeschreven
        titelrij = []
        componentrij = []
        samenstellingrij  = []    
        designrij = []
        #Algemene defenities
        idlijst = []
        curr = []
        # Vul de informatie van de titelrij aan met de juiste custom properties
        for i in range(3):
            tekst = ['Quantity', 'Name', 'Number', 'Description', 'Material','Parent (children)']
            # Zoek twee maal naar de juiste in            
            attribuutGroep = 'custProp_' + str(i)
            tekst += splitsInfo(2, attribuutGroep, design)     # info van stijl
            tekst += splitsInfo(2, 'custProp_3', design)       # info algemeen
            # Voeg extra kolommen in voor munteenheid 
            propType = [''] * 6
            propType += splitsInfo(1, attribuutGroep, design)  
            propType += splitsInfo(1, 'custProp_3', design) 
            PropIds = [''] * 6
            PropIds += splitsInfo(0, attribuutGroep, design)  
            PropIds += splitsInfo(0, 'custProp_3', design)
            if 'Currency' in propType:             
                indexen = [i for i, x in enumerate(propType) if x == 'Currency']
                x = 0
                for elk in indexen:
                    x += 1
                    tekst.insert(elk + x, ' ')
                    uid = PropIds[int(indexen[x-1])]
                    curr.append(uid)                    
            # Plaats het geheel in de rij        
            titelrij.append(tekst)

        # Voeg de juiste lijst aan met info over het onderdeel
        # Vind eerst alle id's van de eigenschappen
        for i in range(4):
            attribuutGroep = 'custProp_' + str(i)
            ids = splitsInfo(0, attribuutGroep, design)    
            idlijst.append(ids)
        # Vind info over onderdelen
        occs = design.rootComponent.allOccurrences
        bom = []
        for occ in occs:
            #definieer dingen
            comp = occ.component
            tekst = []
            # Als dit onderdeel al is behandeld sla de rest dan over
            if comp in bom:
                continue
            bom.append(comp)
            # Laad component data
            qty = 0
            naam = comp.name
            nummer = comp.partNumber
            omschrijving = comp.description
            for occX in occs:
                compX = occX.component
                if compX == comp: qty += 1
            if occ.childOccurrences.count > 0:
                ouderschap = 'True (' + str(occ.childOccurrences.count) + ')'
            else:
                ouderschap = ' '
            if comp.material is not None and comp.material.isValid:
                materiaal = comp.material.name
            else:
                materiaal = ' '
            # data samenvoegen
            tekst = [qty, naam, nummer, omschrijving, materiaal, ouderschap]
            # Zoek de custom Properties
            # Zoek gebruikte stijl
            attribuut = comp.attributes.itemByName('ProppertiesPP', 'PropStijl')
            if attribuut is not None:
                stijl = int(attribuut.value)
            else:
                stijl = 0
            # Vind aantal unieke id's 
            partIdLijst = idlijst[stijl] + idlijst[3]
            # Zoek ingevulde waarden
            for uid in partIdLijst:
                data = comp.attributes.itemByName('ProppertiesPP', uid)
                if data is not None:
                    waarde = data.value
                    if uid in curr:                         #
                        munteenheid = waarde[-3:]           #
                        waarde = waarde[:-3]                #
                        tekst.append(waarde)                #
                        tekst.append(munteenheid)           #
                    else:                                   #
                        tekst.append(waarde)
            # Voeg nu toe aan juiste tabel
            if stijl == 0: componentrij.append(tekst)
            elif stijl == 1: samenstellingrij.append(tekst)
            elif stijl == 2: designrij.append(tekst)
                            
        # Druk de tabellen af
        for i in range(3):
            bestand.writerow(' ')
            # Titelrij en kolomindeling
            titels = [['Parts'], ['Assemblies'], ['Design']]
            bestand.writerow(titels[i])
            bestand.writerow(titelrij[i])
            # Druk rijen af voor de componenten
            tabellen = [componentrij, samenstellingrij, designrij]
            for rij in range(len(tabellen[i])):
                bestand.writerow(tabellen[i][rij])
                
        if trial == True:
            bestand.writerow(' ')
            bestand.writerow(' ')
            bestand.writerow(' ')
            bestand.writerow(['This datasheet has been created using the free evaluation version of Properties++ for Fusion 360.'])
                    
 
       
       
#        bericht = str(tekst)
#        _ui.messageBox(bericht)
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
        
#        #Maak een string voor de titel-rij voor componenten
#        bestand.writerow(['Components and Assemblies'])
#        occs = design.rootComponent.allOccurrences
#        tekst = ['Quantity', 'Name', 'Number', 'Description', 'Material','Parent comp.']
#        # Zoek uit welke stijlen er gebruikt zijn
#        stijlen = []
#        for occ in occs:
#            comp = occ.component
#            stijldata = comp.attributes.itemByName('ProppertiesPP', 'PropStijl')
#            if stijldata is not None:
#                stijl = comp.attributes.itemByName('ProppertiesPP', 'PropStijl').value
#                if stijl not in stijlen:
#                    stijlen.append(stijl)
#        stijlen.append('3')
#        stijlen.sort()
#        # Schrijf benaming van eigenschappen. Schrijf ook direct alle id's op
#        ids = []
#        curr = []
#        for k in stijlen:
#            attribuutGroep = 'custProp_' + str(k)
#            attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
#            if attribuut is not None:
#                attr = attribuut.value
#                attr = attr.split('~~')
#                for each in range(len(attr)-1):
#                    sub = attr[each].split('~')
#                    tekst.append(sub[2])
#                    if sub[1] == 'Currency':
#                        tekst.append('')
#                        curr.append(sub[0])
#                    ids.append(sub[0])
#        bestand.writerow(tekst)
#
#        # Maak een nieuwe rij aan voor elk component
#        bom = []
#        for occ in occs:
#            #definieer dingen
#            comp = occ.component
#            # Als dit onderdeel al is behandeld sla de rest dan over
#            if comp in bom:
#                continue
#            # Voeg toe aan behandelde items
#            bom.append(comp)
#            # Find quantity
#            qty = 0
#            for occX in occs:
#                compX = occX.component
#                if compX == comp: qty += 1
#            tekst.append(qty)
#                        # Laad component data
#            naam = comp.name
#            nummer = comp.partNumber
#            omschrijving = comp.description
#            if occ.childOccurrences.count > 0:
#                ouderschap = 'True (' + str(occ.childOccurrences.count) + ')'
#            else:
#                ouderschap = ' '
#            if comp.material is not None:
#                materiaal = comp.material.name
#            else:
#                materiaal = ' '
#            # data samenvoegen
#            tekst = [qty, naam, nummer, omschrijving, materiaal, ouderschap]
#            #Ga op zoek naar de juiste info. Id-nummers zijn bekend via ids[]
#            for uid in ids:
#                data = comp.attributes.itemByName('ProppertiesPP', uid)
#                if data is not None:
#                    waarde = data.value
#                    if uid in curr:
#                        munteenheid = waarde[-3:]
#                        waarde = waarde[:-3]
#                        tekst.append(waarde)
#                        tekst.append(munteenheid)
#                    else:
#                        tekst.append(waarde)
#                else:
#                    waarde = ''
#                    tekst.append(waarde)
#            # schrijf naar CSV
#            bestand.writerow(tekst)

    # Bericht met vraag of bestand geopend moet worden
    controle = _ui.messageBox('File succesfully saved. Would you like to open the file now?', 'Properties++', 1, 2)
    if controle == False:
        webbrowser.open(bestandsnaam)

def splitsInfo(benodigd, attribuutGroep, design):
    txt = []
#    curr = []
    attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
    if attribuut is not None:
        attr = attribuut.value
        attr = attr.split('~~')
        for each in range(len(attr)-1):
            sub = attr[each].split('~')
            txt.append(sub[benodigd])
#            if sub[1] == 'Currency':
#                txt.append('')
#                curr.append(sub[0])
    return(txt)


def tekstEigenschapnamenToevoegen(attribuut, tekst, sub):
    if attribuut is not None:
        attribuut = attribuut.value.split('~~')
        for x in range(len(attribuut)-1):
            subattr = attribuut[x].split('~')
            tekst.append(subattr[sub])
    return(tekst)

def ManagerOnLoad(args, inputs):
    try:
        if args is not None:        
            cmd = adsk.core.Command.cast(args.command)
        if inputs is None:
            inputs = cmd.commandInputs
        design = adsk.core.Application.get().activeProduct

        # Plaats rijen in tabellen
        for n in range(4):
            attribuutGroep = 'custProp_' + str(n)
            attribuut = design.rootComponent.attributes.itemByName('ProppertiesPP', attribuutGroep)
            if attribuut is not None:
                tekst = attribuut.value
                if tekst != ' ':
                    regel = tekst.split('~~')
                    tabelId = 'idTabel_' + str(n)
                    tableInput = inputs.itemById(tabelId)
                    for i in range(len(regel)-1):
                        param = regel[i]
                        param = param.split('~')
                        addRowToTable(tableInput, param[0], param[1], param[2])

        #Instellingen plaatsen
        # Munteenheid
        try:
            instellingenString = design.rootComponent.attributes.itemByName('ProppertiesPP', 'Instellingen').value
            munteenheidIndex = int(instellingenString.split('~')[0])
            inputs.itemById('idSetMunt').listItems.item(munteenheidIndex).isSelected = True
        except:
            inputs.itemById('idSetMunt').listItems.item(31).isSelected = True


    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))

def volgordeRijdenManager(richting, tableInput):
    if tableInput.rowCount>0:
            
        # Definiëer
        lijstProperties = []
        lijstVolgorde = []
        aantalRijen = tableInput.rowCount
    
        # Creëer lijsten
        for x in range(aantalRijen):
            lijstVolgorde.append(x)             # moet lijst opleveren 1,2,3 enz
            sublijst = []
            propNaam = tableInput.getInputAtPosition(x,0).value
            propType = tableInput.getInputAtPosition(x,1).selectedItem.name
            propId   = tableInput.getInputAtPosition(x,1).id
            propId   = propId.split('_PPP_')[1]
            sublijst.append(propId)
            sublijst.append(propType)
            sublijst.append(propNaam)
            lijstProperties.append(sublijst)
    
    
        # Verander volgorde vn de volgordelijst
        selectieIndex = tableInput.selectedRow
        nieuweIndex = selectieIndex
        if richting == 'Omhoog' and selectieIndex > 0:
            nieuweIndex = selectieIndex - 1
        elif richting != 'Omhoog' and selectieIndex < aantalRijen-1:
            nieuweIndex = selectieIndex + 1
        lijstVolgorde[selectieIndex] = nieuweIndex
        lijstVolgorde[nieuweIndex] = selectieIndex
    
        # Verander volgorde van echte lijst
        lijstProperties = [lijstProperties[i] for i in lijstVolgorde]
    
        # Verwijder alle items in tabel
        for n in range(aantalRijen):
            tableInput.deleteRow(0)
    
        # Plaats items in tabel opnieuw op basis van gemaakte lijst
        for z in range(len(lijstProperties)):
            addRowToTable(tableInput, lijstProperties[z][0], lijstProperties[z][1], lijstProperties[z][2])
        tableInput.selectedRow = nieuweIndex
        

# Adds a new row to the table.
def addRowToTable(tableInput, uId, propType, propName):
    # Get the CommandInputs object associated with the parent command.
    cmdInputs = adsk.core.CommandInputs.cast(tableInput.commandInputs)

    # Increment a counter used to make each row unique.
    global _rowNumber
    _rowNumber = _rowNumber + 1

    # Maak uniek Id aan op basis van optelling (_rownumber) en de datum + tijd
    if uId == '':
        uId = time.strftime("%x")+ time.strftime("%X") + str(_rowNumber)
        verbodenKarakters = '/: '
        for char in verbodenKarakters:
            uId = uId.replace(char,"")
    # Controleer of naam wel of niet al is aangegeven
    if propName == '':
        propName = 'Name'

    # Maak inhoud van tabel aan
    stringInput =  cmdInputs.addStringValueInput('TableInput_string_PPP_{}'.format(uId), 'Name', propName)
    stringInput.tooltip = 'Name of propertie. The name can have a maximum of 15 characters'
    PropType = cmdInputs.addDropDownCommandInput('idPropType_PPP_{}'.format(uId), 'Type', adsk.core.DropDownStyles.LabeledIconDropDownStyle);
    PropType.listItems.add('Text', True, '')
    PropType.listItems.add('Integer', False, '')
    PropType.listItems.add('Number', False, '')
    PropType.listItems.add('Currency', False, '')
    PropType.listItems.add('URL', False, '')
    PropType.listItems.add('Yes/No', False, '')
    PropType.listItems.add('Multiline text', False, '')
    PropType.tooltip = 'Select the data type associated with this property'
    PropType.tooltipDescription = 'Text = Normal text. This can contain anything from numbers to special characters. \n\nInteger = These are real numbers (no decimal places) which can also be zero or have a negative value. \n\nNumber = A number can contain any kind of value. \n\nCurrency = This will contain a Number plus a dropdownmenu for the desired currency. \n\nURL = A URL is a reference to a file online or on your pc. Fill in the full path of the file in the shown textbox. A button will appear to open the file/path. \n\nYes/No = The yes/no parameter will show a checkbox. \n\nMultiline Text = The multiline text can contain the same information as Text but will create a scrollable textbox for larger text inputs.'


    # verander gekozen type als beschikbaar en deactiveer deze
    if propType != '':
        for x in range(PropType.listItems.count):
            if PropType.listItems.item(x).name == propType:
                PropType.listItems.item(x).isSelected = True
                break
        PropType.isEnabled = False
        PropType.tooltip= "Previously created property's cannot change their type to prevent conflicts with existing data."

    # Add the inputs to the table.
    row = tableInput.rowCount
    tableInput.addCommandInput(stringInput, row, 0)
    tableInput.addCommandInput(PropType, row, 1)
    tableInput.selectedRow = row

def propertiesOpslaan(inputs, design):
    try:
        # Maak string aan voor toegevoegde eigenschappe [uid, type en naam]
        for n in range(4):
            tabelId = 'idTabel_' + str(n)
            tableInput = inputs.itemById(tabelId)
            aantalRijen = tableInput.rowCount
            tekst = ''
            if aantalRijen > 0:
                for rij in range(aantalRijen):
                    uid = tableInput.getInputAtPosition(rij,1).id.split('_PPP_')[1]
                    tekst += uid + '~'
                    tekst += tableInput.getInputAtPosition(rij,1).selectedItem.name + '~'
                    naam = tableInput.getInputAtPosition(rij,0).value.lstrip()
                    naam = naam.replace('~', '')
                    tekst += naam[:15] + '~~'
            else:
                tekst = ''
            attribuutGroep = 'custProp_' + str(n)
            design.rootComponent.attributes.add('ProppertiesPP', attribuutGroep, tekst)

        #instellingen opslaan
        standaardMunteenheid = str(inputs.itemById('idSetMunt').selectedItem.index)
        instellingenString = standaardMunteenheid + '~'
        design.rootComponent.attributes.add('ProppertiesPP', 'Instellingen', instellingenString)
    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))


# Event handler for the execute event.
class OkKnopManager(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = adsk.core.Command.cast(args.command)
            inputs = cmd.commandInputs
            design = adsk.core.Application.get().activeProduct

            propertiesOpslaan(inputs, design)

        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))


# Event handler that reacts to any changes the user makes to any of the command inputs.
class MyCommandInputChangedHandler(adsk.core.InputChangedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            ui = adsk.core.Application.get().userInterface
            eventArgs = adsk.core.InputChangedEventArgs.cast(args)
            design = adsk.core.Application.get().activeProduct
            inputs = eventArgs.inputs
            global Component

            for selection in ui.activeSelections:
                selectedEnt = selection.entity

                #Controleer of het geselecteerde object een rootComponent of een subComponent is
                if selectedEnt.objectType == 'adsk::fusion::Occurrence':
                    Component = selectedEnt.component
                elif selectedEnt.objectType == 'adsk::fusion::Component':
                    Component = selectedEnt
                else:
                    continue    #Als het geselecteerde object niet een component of occurence is wordt doorgegeaan naar het volgende object en wordt de rest overgeslagen
               
                # Is de verandering een nieuwe selectie of iets anders?
                if eventArgs.input.id == 'idSelect':
                    ## plaats custom properties. Alle eigenschappen worden geplaatst, onafhankelijk van het filter.
                    #customPropPlaatsen(inputs.itemById('idGroepCustProp').children, inputs)
                    nieuweSelectie(Component, design, selectedEnt, inputs, ui)
                else:                    
                    # Open linked document als op de knop wordt gedrukt
                    if eventArgs.input.id == 'idBtnOpen':
                        # Open linked bestand
                        selDataFile =  selectedEnt.component.parentDesign.parentDocument.dataFile
                        adsk.core.Application.get().documents.open(selDataFile)
                        ui.activeSelections.clear()     #verbreek eventuele selectie
                        # Selecteer juiste onderdeel
                        rootNewComp = adsk.core.Application.get().activeProduct.rootComponent                        
                        if Component.name != rootNewComp.name:
                            designNew = adsk.core.Application.get().activeProduct
                            occs = designNew.rootComponent.allOccurrences  
                            for occ in occs:
                                if occ.component.name == Component.name:
                                    ui.activeSelections.add(occ)
                                    break
                        else:
                            ui.activeSelections.add(adsk.core.Application.get().activeProduct.rootComponent)                       
                        # heropen P++ met juiste selectie    
                        ui.commandDefinitions.itemById('idPPPContextmenu').execute()
                        return
                        
                    # Controleer of custom propstijl is veranderd. Maak onderdelen onzichtbaar die niet bij deze eigenschap horen.
                    if eventArgs.input.id == 'idPropStijl':
                        zichtbaarheidCustProps(inputs, design)

                    # Controleer of iemand een URL probeert te openen
                    argId = eventArgs.input.id
                    butType = argId.split('_')
                    if len(butType) > 2 and butType[2] == 'Link':
                        urlTextboxId = 'CP_' + butType[1]
                        url = inputs.itemById(urlTextboxId).value
                        if url != '' and url != ' ' and url is not None:
                            webbrowser.open_new_tab(url)
                        else:
                            txtBoxNaam = inputs.itemById(urlTextboxId).name
                            ui.messageBox('Please add an URL or filelocation to textbox "' + txtBoxNaam + '" to continue.')
                    
                break       # Voorkomt dat als een lijst van objecten wordt aangevraagd dat dan elk object wordt doorgekeken en alleen de laatste uiteindelijk wordt weergegeen. Break sluit de loop direct en alleen de eerste wordt geselecteerd

        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

def zichtbaarheidCustProps(inputs, design):
    # Wanneer de custom properties geplaatst worden zijn ze allemaal zichtbaar.
    # Verander, nadat de juiste properties-stijl is geselecteerd, de zichbaarheid van de individuele elementen.

    stijlIndex = inputs.itemById('idPropStijl').selectedItem.index
    for x in range(3):
        attribuutGroep = 'custProp_' + str(x)
        ouder = ouderDoc()
        attribuut = ouder.attributes.itemByName('ProppertiesPP', attribuutGroep)
        if attribuut is not None and attribuut.value != ' ':
            attribuutText = attribuut.value
            custProps = attribuutText.split('~~')
            for c in range(len(custProps)-1):
                elementen = custProps[c].split('~')
                cpId = elementen[0]
                cpType = elementen[1]
                commandoId = 'CP_' + cpId
                commandoIdCurrency = commandoId + 'Currency'
                commandoIdLink = commandoId + '_Link'
                if x != stijlIndex:
                    inputs.itemById(commandoId).isVisible = False
                    if cpType == 'Currency':
                        inputs.itemById(commandoIdCurrency).isVisible = False
                    elif cpType == 'URL':
                        inputs.itemById(commandoIdLink).isVisible = False
                else:
                    inputs.itemById(commandoId).isVisible = True
                    if cpType == 'Currency':
                        inputs.itemById(commandoIdCurrency).isVisible = True
                    elif cpType == 'URL':
                        inputs.itemById(commandoIdLink).isVisible = True

                

# Event handler for the execute event.
class OkKnop(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:

            command = args.firingEvent.sender
            inputs = command.commandInputs
            global Component

            # Update standaardgegevens
            Component.partNumber = inputs.itemById('idNumberInput').value
            if inputs.itemById('idNameInput').isEnabled == True:
                Component.name = inputs.itemById('idNameInput').value
            Component.description = inputs.itemById('idDescriptionInput').value

            # Materiaal updaten
            if inputs.itemById('idMatInput').isVisible == True and inputs.itemById('idMatInput').selectedItem is not None:
                Component.material = getMaterial(inputs.itemById('idMatInput').selectedItem.name)

            # Custom Prop gekozen stijl onthouden
            if inputs.itemById('idGroepCustProp').isEnabled == True:
                CompStijl = inputs.itemById('idPropStijl').selectedItem.index
                Component.attributes.add('ProppertiesPP', 'PropStijl', str(CompStijl))

            # Sla de custom properties op. (alleen diegene die beschikbaar zijn ivm filter)
            Lijst = custPropLijst(inputs)
            for n in range(len(Lijst)-1):
                eigenschapId = str(Lijst[n][0])
                inputId = 'CP_' + eigenschapId
                if Lijst[n][1] == 'Text' or Lijst[n][1] == 'Integer' or Lijst[n][1] == 'Number' or Lijst[n][1] == 'URL' or Lijst[n][1] == 'Yes/No':
                    if inputs.itemById(inputId).value is not None and inputs.itemById(inputId).value != '':
                        waarde = str(inputs.itemById(inputId).value)
                        #_ui.messageBox(inputs.itemById(inputId).name + ': ' + waarde)
                    else:
                        waarde = ' '
                elif Lijst[n][1] == 'Currency':
                    inputId2 = inputId + 'Currency'
                    if inputs.itemById(inputId).value is not None and inputs.itemById(inputId).value != '':
                        waarde = str(inputs.itemById(inputId).value) + str(inputs.itemById(inputId2).selectedItem.name)
                    else:
                        waarde = ' ' + str(inputs.itemById(inputId2).selectedItem.name)
                elif Lijst[n][1] == 'Multiline text':
                    if inputs.itemById(inputId).text is not None and inputs.itemById(inputId).text != '':
                        waarde = str(inputs.itemById(inputId).text)
                    else:
                        waarde = ' '
                waarde = waarde.replace('~', '')
                Component.attributes.add('ProppertiesPP', eigenschapId, waarde)


        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

def custPropLijst(inputs):
    #Maak een lijst met alle custom properties die opgeslagen moeten worden.

    ouder = ouderDoc()

    # verzamel alle benodigde eigenschappen in één lange string
    CompStijlIndex = inputs.itemById('idPropStijl').selectedItem.index
    eigenschappenReferentie = 'custProp_' + str(CompStijlIndex)
    eigenschappenGroep1 = ouder.attributes.itemByName('ProppertiesPP', eigenschappenReferentie)
    eigenschappenGroep2 = ouder.attributes.itemByName('ProppertiesPP', 'custProp_3')
    if eigenschappenGroep1 is not None:
        eigenschappenLijst1 = eigenschappenGroep1.value
    else:
        eigenschappenLijst1 = ''
    if eigenschappenGroep2 is not None:
        eigenschappenLijst2 = eigenschappenGroep2.value
    else:
        eigenschappenLijst2 = ''
    eigenschappenLijstTotaal = eigenschappenLijst1 + eigenschappenLijst2

    # Maak lijst
    eigenschappen = eigenschappenLijstTotaal.split('~~')
    eigenschappenNested = []
    for n in range(len(eigenschappen)):
        eigenschap = eigenschappen[n]
        eigenschap = eigenschap.split('~')
        eigenschappenNested.append(eigenschap)

    return(eigenschappenNested)
    #_ui.messageBox(str(len(eigenschappenNested)))

def nieuweSelectie(Component, design, selectedEnt, inputs, ui):
    
    inputs.itemById('idSelect').isVisible = False

    # Bereken fisieke eigenschappen
    physicalProperties = Component.getPhysicalProperties(adsk.fusion.CalculationAccuracy.MediumCalculationAccuracy) #Let op precisie

    # Controleer het type selectie
    IsLinked = CheckLinked(Component, design, selectedEnt, inputs)
    IsSaved =  design.parentDocument.isSaved
    IsSingle = VerwachteComponentStijl(Component, design, 1)

    # Controleer Custom Properties stijl
    try:
        CompStijl = int(float(Component.attributes.itemByName('ProppertiesPP', 'PropStijl').value))
    except:
        CompStijl = VerwachteComponentStijl(Component, design, 0)

    #Maak onderdelen weer bewerkbaar
    if IsLinked == False or IsSaved == False:
        inputs.itemById('idNumberInput').isEnabled = True
        inputs.itemById('idNameInput').isEnabled = True
        inputs.itemById('idDescriptionInput').isEnabled = True
        inputs.itemById('idAreaInput').isEnabled = True
        inputs.itemById('idGewichtInput').isEnabled = True
        inputs.itemById('idVolumeInput').isEnabled = True
        inputs.itemById('idPropStijl').isEnabled = True
    
    # Maak specifieke functies beschikbaar voor gelinkte modellen
    if IsSaved == True and IsLinked == True:
        inputs.itemById('idTxtLinked').isVisible = True
        inputs.itemById('idBtnOpen').isVisible = True
    elif IsLinked == True and IsSaved == False:
        inputs.itemById('idTxtSaveReminder').isVisible = True  
   

    # Vul waardes in van palette naar het geselecteerde onderdeel
    inputs.itemById('idNumberInput').value = Component.partNumber
    inputs.itemById('idNameInput').value = Component.name
    inputs.itemById('idDescriptionInput').value = Component.description
    inputs.itemById('idAreaInput').formattedText = design.unitsManager.formatInternalValue(round(physicalProperties.volume,3), oppEenheid(), True)
    inputs.itemById('idGewichtInput').formattedText = design.unitsManager.formatInternalValue(round(physicalProperties.mass,3), gewichtEenheid(), True)
    inputs.itemById('idVolumeInput').formattedText = design.unitsManager.formatInternalValue(round(physicalProperties.volume,3), volumeEenheid(), True)
    inputs.itemById('idPropStijl').listItems.item(CompStijl).isSelected = True
    zichtbaarheidCustProps(inputs,design)


    #Verberg elementen die niet te gebruiken zijn met huidige selectie
    if IsLinked == True or IsSingle == False:
        inputs.itemById('idMatInput').isVisible = False
        inputs.itemById('idMatError').isVisible = True
        inputs.itemById('idMatInput').isEnabled = False
    else:
        inputs.itemById('idMatInput').isVisible = True
        inputs.itemById('idMatError').isVisible = False
        if Component.material is not None:
            inputs.itemById('idMatInput').listItems.add(Component.material.name, True, '' , 0)
        inputs.itemById('idMatInput').isEnabled = True
    if selectedEnt.objectType == 'adsk::fusion::Component':
        inputs.itemById('idNameInput').isEnabled = False

    # Laad Custom properties in
    Lijst = custPropLijst(inputs)
    for n in range(len(Lijst)-1):
        eigenschapId = str(Lijst[n][0])
        eigenschapType = str(Lijst[n][1])
        eigenschapLocate = Component.attributes.itemByName('ProppertiesPP', eigenschapId)
        if eigenschapLocate is not None:
            eigenschapWaarde = eigenschapLocate.value.lstrip()
            inputId = 'CP_' + eigenschapId
            if eigenschapType == 'Text' or eigenschapType == 'URL':
                inputs.itemById(inputId).value = eigenschapWaarde
            elif eigenschapType == 'Integer':
                inputs.itemById(inputId).value = int(eigenschapWaarde)
            elif eigenschapType == 'Number':
                inputs.itemById(inputId).value = float(eigenschapWaarde)
            elif eigenschapType == 'Currency':
                lengteGetal = len(eigenschapWaarde)-3
                waarde1 = float(eigenschapWaarde[:lengteGetal])
                waarde2 = eigenschapWaarde[-3:]
                inputs.itemById(inputId).value = waarde1
                inputId = inputId + 'Currency'
                currencyLijst = currencyList()
                Lijstplat = []
                for each in range(len(currencyLijst)):
                    Lijstplat.append(currencyLijst[each][0])
                juisteIndex = Lijstplat.index(waarde2)
                inputs.itemById(inputId).listItems.item(juisteIndex).isSelected = True
            elif eigenschapType == 'Yes/No':
                if eigenschapWaarde == 'True': eigenschapWaarde = True 
                else: eigenschapWaarde = False
                inputs.itemById(inputId).value = eigenschapWaarde
            elif eigenschapType == 'Multiline text':
                inputs.itemById(inputId).text = eigenschapWaarde
                


def applyMaterialToEntities(material, entities):
    for entity in entities:
        entity.material = material
    
def CheckLinked(Component, design, selectedEnt, inputs):
    IsLinked = False
       
    if design.rootComponent.name != Component.name:
        if design.parentDocument.name != selectedEnt.component.parentDesign.parentDocument.name:
            IsLinked = True
            
    return(IsLinked)

def VerwachteComponentStijl(Component, design, aanvraag):
    # Definieer filters
    IsMultibody = True
    IsComp = 2                  # 0 = niet waar, 1 = waar, 2 = waarschijnlijk niet, 3 = waarschijnlijk wel
    IsAssy = 0                  # 0 = niet waar, 1 = wel waar, 2 waarschijnlijk niet
    IsProj = True

    # Bepaal of er meerdere bodies zijn
    BodyCount = 0
    for body in Component.bRepBodies:
        BodyCount += 1

    if BodyCount > 1:
        IsMultibody = True
    else:
        IsMultibody = False
    # Controleer of de selectie een samenstelling is
    CompCount = 0
    for i in range(0, Component.occurrences.asList.count):
        CompCount += 1
    if CompCount > 0:
        IsAssy = 1
    elif IsMultibody  == True:
        IsAssy = 2
    else:
        IsAssy = 0
    # Controleer of de selectie het hoofdcomponent is
    if design.rootComponent.name == Component.name:
        IsProj = True
    else:
        IsProj = False
    # Controleer of de selectiel een component is
    if IsMultibody == False and IsAssy == 0:
        IsComp = 1
    elif IsAssy == 1:
        IsComp = 2
    elif IsMultibody == True and IsAssy != 1:
        IsComp = 3
    else:
        IsComp = 2

    if IsProj == True:
        stijl = 2
    elif IsComp == 1:
        stijl = 0
    elif IsAssy == 1:
        stijl = 1
    elif IsComp >= IsAssy:
        stijl = 0
    else:
        stijl = 1

    if aanvraag == 0:
        return(stijl)
    else:
        if IsMultibody == True or IsAssy == 1:
            return(False)
        else:
            return(True)
# Bepaald wat de juiste eenheid is om het gewicht mee uit te drukken
def gewichtEenheid():
    x = adsk.core.Application.get().activeProduct.unitsManager.defaultLengthUnits
    return {
        'mm': 'g',
        'cm': 'g',
        'm': 'kg',
        'cm': 'g',
        'in': 'ouncemass',
        'ft': 'lbmass',
    }[x]
def volumeEenheid():
    x = str(adsk.core.Application.get().activeProduct.unitsManager.defaultLengthUnits) + '^3'
    return(x)
def oppEenheid():
    x = str(adsk.core.Application.get().activeProduct.unitsManager.defaultLengthUnits) + '^2'
    return(x)

class MyCommandDestroyHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            # When the command is done, terminate the script
            # This will release all globals which will remove all event handlers
            adsk.terminate()

        except:
            errorReport('Failed:\n{}'.format(traceback.format_exc()))

# Benodigd om materiaal uit te lezen en aan te passen.
def getMaterialsFromLib(libName, filterExp):
    global materialsMap
    materialList = None
    if libName in materialsMap:
        materialList = materialsMap[libName]
    else:
        materialLib = app.materialLibraries.itemByName(libName)
        materials = materialLib.materials
        materialNames = []
        for material in materials:
            materialNames.append(material.name)
        materialsMap[libName] = materialNames
        materialList = materialNames

    if filterExp and len(filterExp) > 0:
        filteredList = []
        for materialName in materialList:
            if materialName.lower().find(filterExp.lower()) >= 0:
                filteredList.append(materialName)
        return filteredList
    else:
        return materialList
def getMaterialLibNames():
    materialLibs = app.materialLibraries
    libNames = []
    for materialLib in materialLibs:
        if materialLib.materials.count > 0:
            libNames.append(materialLib.name)
    return libNames
def getMaterial(materialName):
    materialLibs = app.materialLibraries
    material = None
    for materialLib in materialLibs:
        materials = materialLib.materials
        try:
            material = materials.itemByName(materialName)
        except:
            pass
        if material:
            break
    return material

def stop(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui  = app.userInterface

        for obj in cmdDefsR:
            if obj.isValid:
                obj.deleteMe()
            else:
                ui.messageBox(str(obj) + ' is not a valid object')
                
        trialStop()

        _handlers.clear()

    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))
            
def errorReport(tekst):
    # Wanneer er error meldingen zijn moeten deze niet aan de gebruiker getoond worden, maar misschien zijn ze wel handig voor latere referentie. 
    # Sla alle fouten op in een extern bestand dat bij het programma wordt opgeslagen.    
    
    if verbergErrors == True:
        try: 
            #Update tekst informatie
            FusionVersie = str(_app.version)
            tekst = time.strftime("%x")+ time.strftime("%X") + '     ' + str(versie) + '     ' + FusionVersie + '     ' + tekst.replace('\n', ';')
            
            # Bestandlocatie
            bestandnaam = bestandLocatie('errorReport')
            
            #Schrijf in bestand
            with open(bestandnaam, 'a+') as bestand:
                bestand.write(tekst + '\n')
        except:
            _ui.messageBox('Error in errorreport:\n{}'.format(traceback.format_exc()))
    else: 
        _ui.messageBox(tekst)
        
def trialGebruik():
    # Als een gebruik de trial-versie gebruikt moet deze om de zoveel keer gebruik een bericht ontvangen dat dit een probeer-versie is. 
    try:
        if trial == True:
            # definiëer
            gebruikerNaam = adsk.core.Application.get().currentUser.displayName            
            global teller
            teller += 1
            
            # Actie als teller te hoog komt
            if teller >= trialBericht:
                antwoord = _ui.messageBox('Hi ' + gebruikerNaam + '! Thank you for using Properties++!\n\nYou are currently running an evaluation version of our software. Although the trial is unlimited, Properties++ is not free software and you must obtain a license for continued use.\n\nWould you like to purchase a licensed version now?', 'Properties++ Trial', 3, 2)
                if antwoord == 2:   # = 2 is ja, 3 is nee
                    webbrowser.open_new_tab('www.cadcollege.com')
                teller = 0
            
            # Als iemand het systeem voor de gek probeert te houden door het log-bestand te veranderen
            if teller < trialStartwaarde:
                teller = 0
    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))
        
def trialStop():
    try:
        if trial == True:
            # definiëer
            gebruikerId = adsk.core.Application.get().currentUser.userId
            
            # Zoek bestandslocatie voor het log bestand
            bestandnaam = bestandLocatie('log') 
            
            #Lees bestand
            data = []
            try: # In geval dat het bestand niet bestaat
                with open(bestandnaam, 'r+') as bestand:            
                    for regel in bestand:
                        regel = regel.strip('\n')
                        data.append(regel)
            except:
                pass
            
            # Verander de gegevens uit het bestand
            gebruikerBestaatAl = False
            for i in range(len(data)):
                data[i] = data[i].split(":")
                if data[i][0] == gebruikerId:
                    data[i][1] = teller
                    gebruikerBestaatAl = True
            if gebruikerBestaatAl == False:
                data.append([gebruikerId,teller])
                        
            # Schrijf data terug naar bestand
            with open(bestandnaam, 'w+') as bestand:
                if len(data) > 0:
                    for i in range(len(data)):
                        bestand.write(data[i][0] + ':' + str(data[i][1]) + '\n')
                else:
                    bestand.write(data[i][0] + ':' + str(data[i][1]) + '\n')
    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))

def bestandLocatie(naam):
    dirname = os.path.dirname(os.path.realpath(__file__))
    bestandnaam = dirname + '\\' + naam + '.txt'
    if '/' in dirname:
        bestandnaam = bestandnaam.replace('\\' , '/')    
    return(bestandnaam)
        
def trialStart():
    try:    
        if trial == True:
            # definiëer
            global teller 
            bestandnaam = bestandLocatie('log') 
            gebruikerId = adsk.core.Application.get().currentUser.userId
            data = []
                
            try: 
                # Lees logbestand en verander waarde van teller naar de waarde in het logbestand
                with open(bestandnaam, 'r+') as bestand:            
                    for regel in bestand:
                        regel = regel.strip('\n')
                        data.append(regel)
                for i in range(len(data)):
                    data[i] = data[i].split(":")
                    if data[i][0] == gebruikerId:
                        teller = int(data[i][1])
            except:
                teller = trialStartwaarde        #Voor de eerste start duurt het langer voordat de gebruiker een melding krijgt.
    except:
        errorReport('Failed:\n{}'.format(traceback.format_exc()))
