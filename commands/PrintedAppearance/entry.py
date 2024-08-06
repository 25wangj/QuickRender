import adsk.core as ad
import adsk.fusion as fs;
import os.path as os
import adsk
from base64 import b64encode
from ...lib import yaml
from ...lib import fusionAddInUtils as futil
from ... import config
from math import *

app = ad.Application.get()
ui = app.userInterface
design = None
CMD_ID = config.ADDIN_NAME + "_PrintedAppearanceCmd"
CMD_NAME = "PrintedAppearance"
CMD_Description = "Add FDM 3D Printed appearance to selected bodies"
IS_PROMOTED = True
WORKSPACE_ID = "FusionSolidEnvironment"
PANEL_ID = "SolidScriptsAddinsPanel"
COMMAND_BESIDE_ID = "ScriptsManagerCommand"
ICON_FOLDER = os.join(os.dirname(os.abspath(__file__)), "icons")
RESOURCES = os.join(os.dirname(os.dirname(os.abspath(__file__))), "resources")
cfgPath = os.join(RESOURCES, "config.yaml")

n = 15
globals = {}

def start():
    cmd_def = ui.commandDefinitions.addButtonDefinition(CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER)
    futil.add_handler(cmd_def.commandCreated, command_created)
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    control = panel.controls.addCommand(cmd_def, COMMAND_BESIDE_ID, False)
    control.isPromoted = IS_PROMOTED

def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()

def command_created(args: ad.CommandCreatedEventArgs):
    globals["command"] = args.command
    inputs = args.command.commandInputs
    cfg = yaml.safe_load(open(cfgPath))

    bodiesInput = inputs.addSelectionInput("bodies", "Bodies", "")
    bodiesInput.addSelectionFilter("SolidBodies")
    bodiesInput.setSelectionLimits(1, 1)
    planeInput = inputs.addSelectionInput("plane", "Base Plane", "")
    planeInput.addSelectionFilter("ConstructionPlanes")
    planeInput.addSelectionFilter("PlanarFaces")
    planeInput.setSelectionLimits(1, 1)
    tol = ad.ValueInput.createByReal(cfg.get("t"))
    inputs.addValueInput("tol", "Meshing Tolerance", "mm", tol)
    height = ad.ValueInput.createByReal(cfg.get("h"))
    inputs.addValueInput("height", "Layer Height", "mm", height)

    inputs.addSeparatorCommandInput("s")

    r = inputs.addIntegerSliderCommandInput("r", "R", 0, 255)
    g = inputs.addIntegerSliderCommandInput("g", "G", 0, 255)
    b = inputs.addIntegerSliderCommandInput("b", "B", 0, 255)
    r.valueOne = cfg.get("r")
    g.valueOne = cfg.get("g")
    b.valueOne = cfg.get("b")
    rough = inputs.addFloatSliderCommandInput("rough", "Roughness", "", 0, 1)
    rough.valueOne = cfg.get("ro")
    refl = inputs.addFloatSliderCommandInput("refl", "Reflectance", "", 0, 1)
    refl.valueOne = cfg.get("re")
    depth = ad.ValueInput.createByReal(cfg.get("d"))
    inputs.addValueInput("depth", "Translucency Depth", "mm", depth)

    globals["execute"] = futil.add_handler(args.command.execute, command_execute)
    globals["destroy"] = futil.add_handler(args.command.destroy, command_destroy)
    globals["terminate"] = futil.add_handler(ui.commandTerminated, command_terminate)
    globals["inputs"] = None
    
def command_execute(args: ad.CommandEventArgs):
    globals["inputs"] = args.command.commandInputs
        
def command_destroy(args: ad.CommandEventArgs):
    pass

def command_terminate(args:ad.ApplicationCommandEventArgs):
    if args.commandId == CMD_ID:
        inputs = globals["inputs"]
        command = globals["command"]
        command.execute.remove(globals["execute"])
        command.destroy.remove(globals["destroy"])
        ui.commandTerminated.remove(globals["terminate"])
        if inputs != None:
            body:fs.BRepBody = inputs.itemById("bodies").selection(0).entity
            plane:ad.Plane = inputs.itemById("plane").selection(0).entity.geometry
            tol = inputs.itemById("tol").value
            height = inputs.itemById("height").value
            r = inputs.itemById("r").valueOne
            g = inputs.itemById("g").valueOne
            b = inputs.itemById("b").valueOne
            rough = inputs.itemById("rough").valueOne
            refl = inputs.itemById("refl").valueOne
            depth = inputs.itemById("depth").value

            cfgNew = dict({
                "r" : r,
                "g" : g,
                "b" : b,
                "t" : tol,
                "h" : height,
                "ro" : rough,
                "re" : refl,
                "d" : depth})
            with open(cfgPath, "w") as out:
                yaml.dump(cfgNew, out)

            design:fs.Design = app.activeProduct
            timeline:fs.Timeline = app.activeProduct.timeline
            start = timeline.count
            comp = body.parentComponent
            calc = body.meshManager.createMeshCalculator()
            calc.surfaceTolerance = tol
            calc.maxNormalDeviation = 45 / n
            tris = calc.calculate()
            mesh = comp.meshBodies.addByTriangleMeshData(tris.nodeCoordinatesAsFloat, tris.nodeIndices, [], [])
            repairInput = comp.features.meshRepairFeatures.createInput(mesh)
            repairInput.meshRepairType = fs.MeshRepairTypes.CloseHolesMeshRepairType
            comp.features.meshRepairFeatures.add(repairInput)

            nodes = mesh.displayMesh.nodeCoordinates
            indices = mesh.displayMesh.nodeIndices
            newIndices = [[] for i in range(2*n + 1)]
            z = plane.normal
            for i in range(len(indices) // 3):
                p1 = nodes[indices[3*i]]
                p2 = nodes[indices[3*i + 1]]
                p3 = nodes[indices[3*i + 2]]
                normal = p1.vectorTo(p2).crossProduct(p1.vectorTo(p3))
                ang = acos(z.dotProduct(normal) / normal.length)
                newIndices[round(2*ang*n / pi)].extend(indices[3*i : 3*i + 3])

            lib = app.materialLibraries.itemByName("QuickRenderMaterials")
            if lib == None:
                lib = app.materialLibraries.load(os.join(RESOURCES, "QuickRenderMaterials.adsklib"))
            apr = design.appearances.itemByName("QuickRender Textured")
            if apr == None:
                apr = design.appearances.addByCopy(lib.appearances.itemByName("Textured"), "QuickRender Textured")
            aprs = [None] * (n + 1)
            for i in range(n + 1):  
                if len(newIndices[n - i]) != 0 or len(newIndices[n + i]) != 0:
                    h = abs(hash((rough, refl, depth)))
                    hStr = b64encode(h.to_bytes(ceil(h.bit_length() / 8))).decode()
                    name = f"QuickRender Printed {height*10 : .2f}mm ({r}, {g}, {b}) {hStr} {i}"
                    aprI = design.appearances.itemByName(name)
                    if aprI == None:
                        aprI = design.appearances.addByCopy(apr, name)
                        aprI.appearanceProperties.itemById("opaque_albedo").value = ad.Color.create(r, g, b, 255)
                        aprI.appearanceProperties.itemById("surface_roughness").value = rough
                        aprI.appearanceProperties.itemById("opaque_f0").value = refl
                        aprI.appearanceProperties.itemById("opaque_mfp").value = depth
                        tex:ad.AppearanceTexture = aprI.appearanceProperties.itemById("surface_normal").value
                        tex.changeTextureImage(os.join(RESOURCES, f"texture_{i}.png"))
                        tex.properties.itemById("texture_RealWorldScaleX").value = height / 2.54
                        tex.properties.itemById("texture_RealWorldScaleY").value = height / 2.54
                    aprs[i] = aprI

            meshes = [None] * (2*n + 1)
            for i in range(2*n + 1):
                if len(newIndices[i]) != 0:
                    meshI = comp.meshBodies.addByTriangleMeshData(mesh.displayMesh.nodeCoordinatesAsFloat, newIndices[i], [], [])
                    meshI.appearance = aprs[abs(n - i)]
                    meshI.name = f"{body.name}_Mesh_{i}"
                    meshes[i] = meshI

            sels = ui.activeSelections
            sels.clear()
            for meshI in meshes:
                if meshI != None:
                    sels.add(meshI)
            sels.add(comp.zConstructionAxis)

            
            
            mat = ad.Matrix3D.create()
            mat.setWithCoordinateSystem(plane.origin, z, plane.uDirection, plane.vDirection)
            for meshI in meshes:
                if meshI != None:
                    meshI.textureMapControl.transform = mat
            #mesh.isLightBulbOn = False
            #body.isLightBulbOn = False
            #timeline.timelineGroups.add(start, timeline.count - 1).name = "Printed Appearance"
