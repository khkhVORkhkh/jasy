#
# Jasy - Web Tooling Framework
# Copyright 2010-2012 Zynga Inc.
#

import logging, re, json, os, fnmatch
from os.path import basename, dirname, relpath, normpath

from jasy.env.File import *
from jasy.core.Project import Project
from jasy.env.State import session, getPermutation, prependPrefix
from jasy.asset.Asset import Asset
from jasy.core.Error import JasyError
from jasy.core.Util import sha1File, getKey

__all__ = ["AssetManager"]


class AssetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Asset):
            return obj.export()
            
        return json.JSONEncoder.default(self, obj)
        


class AssetManager:
    """
    Manages assets aka images, styles and other files required for a web application.
    
    Supports filtering assets based on a given class list (with optional permutation) to
    only include and copy assets which are needed by the current implementation. This is 
    especially useful when only parts of dependend projects are actually used.
    
    Merges assets with the same name from different projects. But normally each project
    creates it's own sandbox namespace so this has not often any effect at all.
    
    Supports images and automatically detect their size and image format. Both informations
    are added to the exported data later on.
    """
    
    def __init__(self, classes):
        self.__classes = classes
        self.__permutation = getPermutation()
        
        # Initialize storage pool
        assets = self.__assets = {}
        
        # Returns the regular expression object to use for filtering
        expr = self.__compileFilterExpr()
        
        # Loop though all projects and merge/filter assets
        for project in session.getProjects():
            projectAssets = project.assets
            for fileId in projectAssets:
                # Minor performance tweak: Using lookup instead of regexp during merge
                if fileId in assets or expr.match(fileId):
                    assets[fileId] = projectAssets[fileId]
        
        
        

        self.__processSprites()
        self.__processAnimations()
        
        logging.debug("Selected classes make use of %s assets" % len(assets))
        
        
        
        
    def __processSprites(self):
        
        assets = self.__assets
        configs = [fileId for fileId in assets if assets[fileId].isImageSpriteConfig()]
        logging.info("Processing %s images sprite configs...", len(configs))
        
        for fileId in configs:
            logging.info("- Processing image sprite data from %s", fileId)
            
            asset = assets[fileId]
            spriteBase = dirname(fileId)
                
            try:
                spriteConfig = json.loads(asset.getText())
            except ValueError as err:
                raise JasyError("Could not parse jasysprite.json at %s: %s" % (fileId, err))
                
            for spriteImage in spriteConfig:
                spriteImageId = "%s/%s" % (spriteBase, spriteImage)
                
                singleRelPaths = spriteConfig[spriteImage]
                logging.info("  - Image %s combines %s images", spriteImageId, len(singleRelPaths))

                for singleRelPath in singleRelPaths:
                    singleId = "%s/%s" % (spriteBase, singleRelPath)
                    singleData = singleRelPaths[singleRelPath]

                    if singleId in assets:
                        singleAsset = assets[singleId]
                    else:
                        logging.info("Creating new asset: %s", singleId)
                        singleAsset = Asset(None)
                        assets[singleId] = singleAsset
                        # TODO
                        
                    
                    singleAsset.addSpriteData(spriteImageId, singleData["left"], singleData["top"])
                    
                    if "width" in singleData and "height" in singleData:
                        singleAsset.addDimensionData(singleData["width"], singleData["height"])
                    
                    # Verify that sprite sheet is up-to-date
                    if "checksum" in singleData:
                        fileChecksum = singleAsset.getChecksum()
                        storedChecksum = singleData["checksum"]
                        
                        logging.info("Checksum Compare: %s <=> %s", fileChecksum[0:6], storedChecksum[0:6])
                        
                        if storedChecksum != fileChecksum:
                            raise JasyError("Sprite Sheet is not up-to-date. Checksum of %s differs.", singleId)
        
            logging.debug("  - Deleting sprite config from assets: %s", fileId)
            del assets[fileId]
        
        
        
    def __processAnimations(self):
        
        assets = self.__assets
        configs = [fileId for fileId in assets if assets[fileId].isImageAnimationConfig()]
        logging.info("Processing %s image animation configs...", len(configs))
        
        for fileId in configs:
            logging.info("- Processing image animation data from %s", fileId)
        
            asset = assets[fileId]
            base = dirname(fileId)
                
            try:
                config = json.loads(asset.getText())
            except ValueError as err:
                raise JasyError("Could not parse jasyanimation.json at %s: %s" % (fileId, err))
            
            for relPath in config:
                imageId = "%s/%s" % (base, relPath)
                data = config[relPath]
                
                if not imageId in assets:
                    raise JasyError("Unknown asset %s in %s" % (imageId, fileId))
                
                animationAsset = assets[imageId]
                
                if "rows" in data or "columns" in data:
                    rows = getKey(data, "rows", 1)
                    columns = getKey(data, "columns", 1)
                    frames = getKey(data, "frames")
                    
                    animationAsset.addAnimationData(columns, rows, frames)
                    
                    if frames is None:
                        frames = rows * columns
                    
                elif "layout" in data:
                    layout = data["layout"]
                    animationAsset.addAnimationData(None, None, layout=layout)
                    frames = len(layout)
                    
                else:
                    raise JasyError("Invalid image frame data for: %s" % imageId)

                logging.info("  - Registered animation %s with %s frames", imageId, frames)

            logging.debug("  - Deleting animation config from assets: %s", fileId)
            del assets[fileId]
        
        
        
        
    def __structurize(self, data):
        """
        This method structurizes the incoming data into a cascaded structure representing the
        file system location (aka file IDs) as a tree. It further extracts the extensions and
        merges files with the same name (but different extensions) into the same entry. This is
        especially useful for alternative formats like audio files, videos and fonts. It only
        respects the data of the first entry! So it is not a good idea to have different files
        with different content stored with the same name e.g. content.css and content.png.
        """
        
        root = {}
        
        # Easier to debug and understand when sorted
        for fileId in sorted(data):
            current = root
            splits = fileId.split("/")
            
            # Extract the last item aka the filename itself
            basename = splits.pop()
            
            # Find the current node to store info on
            for split in splits:
                if not split in current:
                    current[split] = {}
                elif type(current[split]) != dict:
                    raise JasyError("Invalid asset structure. Folder names must not be identical to any filename without extension: \"%s\" in %s" % (split, fileId))
                    
                current = current[split]
            
            # Create entry
            logging.debug("Adding %s..." % fileId)
            current[basename] = data[fileId]
        
        return root
    
    
    
    def __compileFilterExpr(self):
        # Merge asset hints from all classes and remove duplicates
        hints = set()
        for classObj in self.__classes:
            hints.update(classObj.getMetaData(self.__permutation).assets)
        
        # Compile filter expressions
        matcher = "^%s$" % "|".join(["(%s)" % fnmatch.translate(hint) for hint in hints])
        logging.debug("Matching assets using: %s" % matcher)
        
        return re.compile(matcher)
        
        
        
    def deployBuild(self, assetFolder="asset"):
        """Deploys all asset files to the destination asset folder"""

        assets = self.__assets
        projects = session.getProjects()

        logging.info("Publishing files...")
        
        copyAssetFolder = prependPrefix(assetFolder)
        
        counter = 0
        for fileId in assets:
            srcFile = assets[fileId].getPath()
            dstFile = os.path.join(copyAssetFolder, fileId.replace("/", os.sep))
            
            if updateFile(srcFile, dstFile):
                counter += 1
        
        logging.info("Updated %s/%s files" % (counter, len(assets)))



    def exportBuild(self, assetFolder="asset", urlPrefix=""):
        """
        Publishes the selected files to the destination folder. This merges files from 
        different projects to this one folder. This is ideal for preparing the final deployment.
        
        - assetFolder: Name of local asset folder
        - urlPrefix: A URL which should be mapped to the project's root folder
        """

        assets = self.__assets
        result = {}
        
        # Processing assets
        for fileId in assets:
            asset = assets[fileId]
            exported = asset.export()
            
            if exported is None:
                # short value to allow simple lookup checks in JS
                result[fileId] = 1
            else:
                result[fileId] = exported
        
        # Figuring out root
        root = urlPrefix
        if root and root[-1] != "/":
            root += "/"
        root += assetFolder
        if root and root[-1] != "/":
            root += "/"
            
        # Structurize
        try:
            structured = self.__structurize(result)
        except Exception:
            logging.error("Could not export build data of assets")
            raise
            
        # Exporting data
        export = toJson({
            "assets" : structured,
            "deployed" : True,
            "root" : root
        })
        
        return export



    def exportSource(self, urlPrefix=""):
        """ 
        Exports asset data for the source version using assets from their original paths.
        - urlPrefix: Useful when a CDN should be used. Maps the project's root to a URL.
        """
        
        main = session.getMain()
        assets = self.__assets
        result = {}
        
        # Processing assets
        for fileId in assets:
            asset = assets[fileId]
            path = main.toRelativeUrl(asset.getPath())
            exported = asset.export()

            if exported is None:
                result[fileId] = [path]
            else:
                result[fileId] = exported + [path]
        
        # Figuring out global root
        root = urlPrefix
        if root and root[-1] != "/":
            root += "/"

        # Structurize
        try:
            structured = self.__structurize(result)
        except Exception:
            logging.error("Could not export build data of assets")
            raise

        # Exporting data
        export = toJson({
            "assets" : structured,
            "deployed" : False,
            "root": root
        })

        return export

