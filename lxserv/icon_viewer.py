"""

    Plug-in Icon Presets.

    Copyright (c) 2008-2021 The Foundry Group LLC
    Copyright (c) 2024 Andreas Rånman

    Permission is hereby granted, free of charge, to any person obtaining a
    copy of this software and associated documentation files (the "Software"),
    to deal in the Software without restriction, including without limitation
    the rights to use, copy, modify, merge, publish, distribute, sublicense,
    and/or sell copies of the Software, and to permit persons to whom the
    Software is furnished to do so, subject to the following conditions:
    
    The above copyright notice and this permission notice shall be included in
    all copies or substantial portions of the Software.   Except as contained
    in this notice, the name(s) of the above copyright holders shall not be
    used in advertising or otherwise to promote the sale, use or other dealings
    in this Software without prior written authorization.
    
    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.

    See colorSynthPath in SDK samples, as well as cloudPB in your Modo install
    folder for other implementations.

"""

import os
from xml.etree import ElementTree
from time import time

import lx
import lxifc
import lxu.command
import lxu.attributes


ICONVIEWERPRESET_NAME = "IconViewerPB"
ICONVIEWERPRESET_ENTRYNAME = ICONVIEWERPRESET_NAME+"Entry"
ICONVIEWERPRESET_PRESETTYPE = ICONVIEWERPRESET_NAME+"PresetType"
ICONVIEWERPRESET_PRESETMETRICS = ICONVIEWERPRESET_NAME+"Metrics"
ICONVIEWERPRESET_SYNTH = "["+ICONVIEWERPRESET_NAME+"]"


class IconViewerPBSyntheticEntry(lxifc.DirCacheSyntheticEntry):  # pylint: disable=too-many-instance-attributes
    """ Synthetic entry for each icon found we will create an instance of this as well as a root instance. """
    def __init__(self, path: str, name: str, is_file: bool, size: "tuple[int, int, int, int]", resource: str):
        self.path = path
        self.name = name
        self.is_file = is_file
        self.x, self.y, self.width, self.height = size
        self.resource = resource

        self.tooltip = resource
        self.modtime = time()

        self.files = []
        self.dirs = []


    def dcsyne_Path(self) -> str:
        """ Entry path. Always starts with "[IconViewerPB]:"

        The C++ sample stores the path to the entry and its name separately, but I find just storing the
        path to work.
        """
        return self.path

    def dcsyne_Name(self) -> str:
        """ Name of the preset or the directory. Directories must be separated with forward slashes.
        Return the name portion of the path. This represents the filename of the entry. 

        We only dump all the icons into the root so we don't really deal much with directories. 
        """
        return self.name

    def dcsyne_DirUsername(self) -> str:
        """ Username of the directory as seen in the preset browser. """
        return self.name

    def dcsyne_DirCount(self, list_mode: int) -> int:
        """ Get the number of files/dirs inside a directory. List mode is one of vDCELIST_DIRS,
        vDCELIST_FILES or vDCELIST_BOTH. Since BOTH resolves to DIRS | FILES, we just test the bits. """
        count = 0
        if list_mode & lx.symbol.vDCELIST_FILES:
            count += len(self.files)
        if list_mode & lx.symbol.vDCELIST_DIRS:
            count += len(self.dirs)
        return count

    def dcsyne_DirByIndex(self, list_mode: int, index: int):
        """ Get a child entry in a directoy given an index and a list mode. We return dirs then files when
        in BOTH mode. """
        if (list_mode & lx.symbol.vDCELIST_DIRS) and index < len(self.dirs):
            return self.dirs[index]
        elif list_mode & lx.symbol.vDCELIST_FILES:
            return self.files[index - len(self.dirs)]
        else:
            lx.throw(lx.symbol.e_FAILED)

    def dcsyne_IsFile(self):
        """ is entry a directory or a file. Returns true for file or false for dirs. """
        return self.is_file

    def dcsyne_Size(self):
        """ Return the 'file size'. We don't have a size so we just return 0.0

        Modo expects a double in order to support file sizes larger than 4gb, but does not expect fractional
        values.
        """
        return 0.0

    def dcsyne_ModTime(self) -> str:
        """ Check the time in order to know if the entry has changed. Not sure if we need to do this."""
        return str(int(self.modtime))


class IconViewerPBSynthetic(lxifc.DirCacheSynthetic):
    """ Synthetic cache is managing the different entries, from the root path of [IconViewerPB]: entries are
    IconViewerPBSyntheticEntry instances.

    Synthetics are only instanced once.

    """

    _instance: "IconViewerPBSynthetic"

    @classmethod
    def get_instance(cls):
        """ As this is supposed to be a singleton, we add a class method for getting existing instance. """
        return cls._instance

    def __init__(self):
        """ This is all executed on startup, so will likely lead to longer start up times for Modo
        as it could take a second to parse all configs. """
        IconViewerPBSynthetic._instance = self
        self.root = IconViewerPBSyntheticEntry(ICONVIEWERPRESET_SYNTH, "", False, size=(0, 0, 0, 0), resource="")

        file_service = lx.service.File()
        platform_service = lx.service.Platform()

        import_paths = [platform_service.ImportPathByIndex(i) for i in range(platform_service.ImportPathCount())]

        images = {}
        icons = set()

        # Attempt parse all configs and get all Image and Icon entries.
        for import_path in import_paths:
            for filename in os.listdir(import_path):
                if not filename.lower().endswith(".cfg"):
                    continue

                config_path = os.path.join(import_path, filename)

                try:
                    root = ElementTree.parse(config_path)
                    _images = root.findall('.//atom[@type="UIElements"]/hash[@type="Image"]')
                    for image in _images:
                        image_path = file_service.ToLocalAlias(image.text.strip())
                        if not os.path.isabs(image_path):
                            image_path = os.path.join(import_path, image_path)
                        if os.path.isfile(image_path):
                            images[image.get('key')] = image_path

                    _icons = root.findall('.//atom[@type="UIElements"]/hash[@type="Icon"]')
                    for icon in _icons:
                        key = icon.get('key', '')
                        if not key:
                            lx.out(f"No key for icon in {config_path}")
                            continue

                        # source will reference a registered image resource,
                        source = icon.find('atom[@type="Source"]')

                        # The x,y and width height will be stored as either a location, or grid entry
                        location = icon.find('atom[@type="Location"]')
                        grid = icon.find('atom[@type="Grid"]')

                        # If it's a location, the x and y will be exact pixels icon starts at
                        if isinstance(location, ElementTree.Element):
                            x, y, w, h = [int(x) for x in location.text.strip().split(' ') if x]
                        # Otherwise if it's defined as a grid, it will say sample icon x y in row col of
                        # icons with same size.
                        elif isinstance(grid, ElementTree.Element):
                            x, y, w, h = [int(x) for x in grid.text.strip().split(' ') if x]
                            x *= w
                            y *= h
                        else:
                            lx.out(f"No location or grid specified for icon in {config_path}")
                            continue

                        icons.add((key, source.text.strip(), (x, y, w, h)))

                except ElementTree.ParseError:
                    lx.out(f"Failed to parse {config_path}")

        for key, resource, size in icons:
            image_path = images.get(resource, '')
            if not image_path:
                continue  # failed to parse the source location for this image,

            entry = IconViewerPBSyntheticEntry(
                path=ICONVIEWERPRESET_SYNTH + ":" + key,
                name=key,
                is_file=True,
                size=size,
                resource=image_path
            )

            self.root.files.append(entry)

    def dcsyn_Lookup(self, path: str) -> IconViewerPBSyntheticEntry:
        """ Lookup for synthetic entry from path. The path will always start with [IconViewerPB]: or else it
        wouldn't be in our hierarchy. """
        if not path.startswith(ICONVIEWERPRESET_SYNTH):
            lx.throw(lx.symbol.e_NOTAVAILABLE)

        # return root if path matches root,
        if path in (ICONVIEWERPRESET_SYNTH, ICONVIEWERPRESET_SYNTH + ":"):
            return self.root

        # split the path to get each level in the tree
        _, relative_path = path.split(":", 1)

        current = self.root
        if '/' in relative_path:
            for part in relative_path.split('/'):
                found = False
                for file in current.files:
                    if part == file.name:
                        current = file
                        found = True

                for directory in current.dirs:
                    if part == directory.name:
                        current = directory
                        found = True

                if not found:
                    lx.throw(lx.symbol.e_NOTAVAILABLE)
        else:
            found = False
            for file in current.files:
                if relative_path == file.name:
                    current = file
                    found = True

            for directory in current.dirs:
                if relative_path == directory.name:
                    current = directory
                    found = True

            if not found:
                lx.throw(lx.symbol.e_NOTAVAILABLE)

        return current

    def dcsyn_Root(self):
        """ Get the synthetic root, which matches the path [IconViewerPB]: """
        return self.root


lx.bless(
    IconViewerPBSynthetic,
    ICONVIEWERPRESET_NAME,
    {lx.symbol.sDCSYNTH_BACKING: lx.symbol.sDCSYNTH_BACKING_MEMORY}
)


class IconViewerPresetType(lxifc.PresetType):
    """ The preset type for a synthetic is just like one for an on-disk preset. We only recognize presets
    that start with our root path [IconViewerPB]:.

    There is no need to look at the contents of the "file", because anything in that path is defined by us. """
    def ptyp_Recognize(self, path: str) -> str:
        """ Recognize 'claims' any path that starts with [IconViewerPB]: and should return the category name."""
        if not path.startswith(ICONVIEWERPRESET_SYNTH):
            lx.notimpl()
        return ICONVIEWERPRESET_SYNTH

    # pylint: disable=too-many-arguments,unused-argument
    def ptyp_Metrics(self, path: str, flags: int, width: int, height: int, previous_metrics: lx.object.Unknown):
        """ Generating metrics is only needed if the previous metrics provided were null.

        Our metrics don't change so if non-null we can just return the previous metrics again. If there are
        no previous metrics, we create new metrics and return those instead.

        The flags indicate the kind of information request by the dir cache. If ..."""
        entry = IconViewerPBSynthetic.get_instance().dcsyn_Lookup(path)
        return IconViewerPresetMetrics(entry, width, height)

    def ptyp_GenericThumbnailResource(self, path: str):
        """ The generic thumbnails is defined as an image resource in the configs, and is used when the
        preset doesn't define its own thumbnail image or the image isn't ready yet. We just want to use
        a generic one but really this will never be called for our presets... """
        return "item.thumbnail.undefined"


lx.bless(IconViewerPresetType, ICONVIEWERPRESET_PRESETTYPE, {
    lx.symbol.sSRV_USERNAME: "Icon Viewer",             # Username of the preset browser, should be defined in
                                                        # message table
    lx.symbol.sPBS_CATEGORY: ICONVIEWERPRESET_NAME,     # Preset category,
    lx.symbol.sPBS_CANAPPLY: "false",                   # don't support Apply(), legacy replaced with drop servers,
    lx.symbol.sPBS_CANDO: "false",                      # don't support Do(), double-clicking on the preset fires
                                                        # preset.do command
    lx.symbol.sPBS_DYNAMICTHUMBNAILS: "true",           # Thumbnail is dynamic, do not cache it to disc always ask
                                                        # for new thumb
    lx.symbol.sPBS_SYNTHETICSUPPORT: "true"             # supports synthetic paths. If false only works on real
                                                        # files on disk
})


class IconViewerPresetMetrics(lxifc.PresetMetrics):
    """ Metrics return specific information for a given preset.

    This includes the metadata (name/description/caption) metadata and markup.

    Metadata is defined as being an inherent property of the file, such as its name, author, creation date
    and so on, while markup is defined by the user of the preset, such as start ratings or favorites."""
    def __init__(self, entry: IconViewerPBSyntheticEntry, width: int, height: int):
        self.entry = entry
        self.width = width
        self.height = height

        self.metadata = lxu.attributes.DynamicAttributes()
        self.metadata.dyna_Add(lx.symbol.sPBMETA_LABEL, lx.symbol.sTYPE_STRING)
        self.metadata.attr_SetString(0, entry.name)

        self.metadata.dyna_Add(lx.symbol.sPBMETA_CAPTION, lx.symbol.sTYPE_STRING)
        self.metadata.attr_SetString(1, f"({self.entry.x}, {self.entry.y}, {self.entry.width}, {self.entry.height})")

        if entry.tooltip:
            self.metadata.dyna_Add(lx.symbol.sPBMETA_TOOLTIP, lx.symbol.sTYPE_STRING)
            self.metadata.attr_SetString(2, entry.tooltip)

    def pmet_Flags(self) -> int:
        return 0

    def pmet_Metadata(self):
        if not self.metadata:
            lx.notimpl()
        return self.metadata

    def pmet_ThumbnailImage(self):
        image_service = lx.service.Image()

        if not os.path.isfile(self.entry.resource):
            lx.notimpl()

        # load the image resource the icon is using,
        resource = image_service.Load(self.entry.resource)
        w, h = resource.Size()
        fmt = resource.Format()

        # would love to just be able to use this method
        # but it seem to freeze the preset browser ...
        # icon = image_service.CreateCrop(
        #     resource,
        #     self.entry.x / w,
        #     self.entry.y / h,
        #     self.entry.width / w,
        #     self.entry.height / h,
        # )

        image = image_service.Create(
            self.entry.width,
            self.entry.height,
            resource.Format(),
            0
        )

        image_write = lx.object.ImageWrite(image)

        # TODO: add any other formats that icons are using. These were all the needed ones for default icons.
        if fmt in (lx.symbol.iIMP_RGBA32, lx.symbol.iIMP_IRGBA32):
            pixel = lx.object.storage('b', 4)
        elif fmt == lx.symbol.iIMP_RGB24:
            pixel = lx.object.storage('b', 3)
        else:
            lx.out(f'pixel format not implemented in icon browser for resource {self.entry.resource}:{fmt}')
            lx.notimpl()

        # Index out of bounds check, print information about which icon is causing the issue,
        if (self.entry.x + self.entry.width) > w:
            lx.out(f"X of range in {self.entry.name} image {self.entry.resource}")
            lx.notimpl()
        if (self.entry.y + self.entry.height) > h:
            lx.out(f"Y of range in {self.entry.name} image {self.entry.resource}")
            lx.notimpl()

        for y in range(self.entry.y, self.entry.y + self.entry.height):
            for x in range(self.entry.x, self.entry.x + self.entry.width):
                resource.GetPixel(x, y, fmt, pixel)
                image_write.SetPixel(x - self.entry.x, y - self.entry.y, fmt, pixel)

        return image

    def pmet_ThumbnailIdealSize(self):
        """ Return the ideal size of the thumbnail """
        return self.entry.width, self.entry.height
