#
# Copyright (c) 2010 rPath, Inc.
#
# This program is distributed under the terms of the Common Public License,
# version 1.0. A copy of this license should have been distributed with this
# source file in a file called LICENSE. If it is not present, the license
# is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
#
# This program is distributed in the hope that it will be useful, but
# without any warranty; without even the implied warranty of merchantability
# or fitness for a particular purpose. See the Common Public License for
# full details.
#

from conary import versions
from conary.build import defaultrecipes, macros, use
from conary.build.grouprecipe import _BaseGroupRecipe, _SingleGroup
from conary.build.recipe import loadMacros
from conary.conaryclient import troveset
from conary.repository import searchsource
from conary.deps import deps

class GroupTupleSetMethods(object):

    def union(self, *troveSetList):
        return self._action(*troveSetList, ActionClass = GroupUnionAction)

    __add__ = union
    __or__ = union

class GroupDelayedTroveTupleSet(GroupTupleSetMethods,
                                troveset.DelayedTupleSet):

    pass

class GroupSearchSourceTroveSet(troveset.SearchSourceTroveSet):

    def find(self, troveSpec):
        return self._action(troveSpec, ActionClass = GroupFindAction)

    __getitem__ = find


class GroupFindAction(troveset.FindAction):

    resultClass = GroupDelayedTroveTupleSet

class GroupUnionAction(troveset.UnionAction):

    resultClass = GroupDelayedTroveTupleSet

class SG(_SingleGroup):

    def __init__(self, *args, **kwargs):
        _SingleGroup.__init__(self, *args, **kwargs)
        self.autoResolve = False
        self.depCheck = False
        self.imageGroup = False

    def iterAddSpecs(self):
        return []

    def iterAddAllSpecs(self):
        return []

    def iterReplaceSpecs(self):
        return []

    def iterDifferenceSpecs(self):
        return []

    def iterNewGroupList(self):
        return []

    def iterNewGroupDifferenceList(self):
        return []

    def iterCopiedFrom(self):
        return []

    def getComponentsToMove(self):
        return []

    def getRequires(self):
        return deps.DependencySet()

    def isEmpty(self):
        return not self.troves

class _GroupSetRecipe(_BaseGroupRecipe):

    Flags = use.LocalFlags
    internalAbstractBaseClass = 1

    def __init__(self, repos, cfg, label, flavor, laReposCache, srcdirs=None,
                 extraMacros={}, lightInstance = False):

        klass = self._getParentClass('_BaseGroupRecipe')
        klass.__init__(self, laReposCache = laReposCache,
                       srcdirs = srcdirs,
                       lightInstance = lightInstance,
                       cfg = cfg)

        self.troveSource = repos
        self.repos = repos

        self.labelPath = [ label ]
        self.buildLabel = label
        self.flavor = flavor
        self.searchSource = searchsource.NetworkSearchSource(
                repos, self.labelPath, flavor)
        self.macros = macros.Macros(ignoreUnknown=lightInstance)
        self.world = GroupSearchSourceTroveSet(self.searchSource)
        self.g = troveset.OperationGraph()

        baseMacros = loadMacros(cfg.defaultMacros)
        self.macros.update(baseMacros)
        for key in cfg.macros:
            self.macros._override(key, cfg['macros'][key])
        self.macros.name = self.name
        self.macros.version = self.version
        if '.' in self.version:
            self.macros.major_version = '.'.join(self.version.split('.')[0:2])
        else:
            self.macros.major_version = self.version
        if extraMacros:
            self.macros.update(extraMacros)

        newGroup = SG(self.name)
        self._addGroup(self.name, newGroup)
        self._setDefaultGroup(newGroup)

    def getLabelPath(self):
        return self.labelPath

    def getSearchFlavor(self):
        return self.flavor

    def iterReplaceSpecs(self):
        return []

    def getResolveTroveSpecs(self):
        return []

    def getChildGroups(self, groupName = None):
        return []

    def getGroupMap(self, groupName = None):
        return {}

    def _getSearchSource(self):
        return self.troveSource

    def getSearchPath(self):
        return [ ]

    def install(self, troveSet):
        self.g.realize()
        for troveInfo in troveSet.l:
            self.defaultGroup.addTrove(troveInfo, True, True, [])

    def available(self, troveSet):
        self.g.realize()
        for troveInfo in troveSet.l:
            self.defaultGroup.addTrove(troveInfo, True, False, [])

    def writeDotGraph(self, path):
        self.g.generateDotFile(path, edgeFormatFn = lambda a,b,c: c)

    def Repository(self, labelList, flavor):
        if type(labelList) == tuple:
            labelList = list(tuple)
        elif type(labelList) != list:
            labelList = [ labelList ]

        for i, label in enumerate(labelList):
            if type(label) == str:
                labelList[i] = versions.Label(label)
            elif not isinstance(label, versions.Label):
                raise CookError("String label or Label object expected")

        if type(flavor) == str:
            flavor = deps.parseFlavor(flavor)

        searchSource = searchsource.NetworkSearchSource(
                                            self.repos, labelList, flavor)
        return GroupSearchSourceTroveSet(searchSource, graph = self.g)

from conary.build.packagerecipe import BaseRequiresRecipe
exec defaultrecipes.GroupSetRecipe
