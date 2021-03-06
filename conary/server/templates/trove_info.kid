<?xml version='1.0' encoding='UTF-8'?>
<?python
#
# Copyright (c) SAS Institute Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from urllib import quote
import time
?>
<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:py="http://purl.org/kid/ns#"
      py:extends="'library.kid'">
    <table py:def="sourceTroveInfo(trove)" class="vheader">
        <tr class="even"><td>Trove name:</td><td>${trove.getName()}</td></tr>
        <tr class="odd"><td>Change log:</td>
            <td>
                <?python
                    cl = trove.getChangeLog()
                    timestamp = time.ctime(trove.getVersion().timeStamps()[-1])
                ?>
                <div><i>${timestamp}</i> by <i>${cl.getName()} (${cl.getContact()})</i></div>
                <p><code>${cl.getMessage()}</code></p>
            </td>
        </tr>
    </table>

    <table py:def="binaryTroveInfo(trove)" class="vheader">
        <?python
        sourceVersion = str(trove.getVersion().getSourceVersion())
        sourceLink = "troveInfo?t=%s;v=%s" % (quote(trove.getSourceName()), quote(sourceVersion))
        ?>
        <tr class="even"><td>Trove name:</td><td>${trove.getName()}</td></tr>
        <tr class="odd"><td>Version:</td><td>${trove.getVersion().asString()}</td></tr>
        <tr class="even"><td>Flavor:</td><td>${trove.getFlavor()}</td></tr>
        <tr class="odd"><td>Built from trove:</td><td><a href="${sourceLink}">${trove.getSourceName()}</a></td></tr>
        <?python
           buildTime = trove.getBuildTime()
           if not buildTime:
               buildTime = '(unknown)'
           else:
               buildTime = time.ctime(buildTime)
        ?>
        <tr class="even"><td>Build time:</td><td>${buildTime} using Conary ${trove.getConaryVersion()}</td></tr>
        <tr class="odd"><td>Provides:</td>
            <td class="top">
                <div py:for="dep in str(trove.provides.deps).split('\n')">${dep.decode('utf8', 'replace')}</div>
                <div py:if="not trove.provides.deps">
                    Trove satisfies no dependencies.
                </div>
            </td>
        </tr>
        <tr class="even"><td>Requires:</td>
            <td>
                <div py:for="dep in str(trove.requires.deps).split('\n')">${dep.decode('utf8', 'replace')}</div>
                <div py:if="not trove.requires.deps">
                    Trove has no requirements.
                </div>
            </td>
        </tr>
    </table>

    <head/>
    <body>
        <div id="inner">
            <h3>Trove Information:</h3>

            <table py:if="metadata">
                <tr class="even"><td>Summary:</td><td>${metadata.getShortDesc()}</td></tr>
                <tr class="odd"><td>Description:</td><td>${metadata.getLongDesc()}</td></tr>
                <tr class="even">
                    <td>Categories:</td>
                    <td><div py:for="category in metadata.getCategories()" py:content="category"/></td>
                </tr>
                 <tr class="odd">
                    <td>Licenses:</td>
                    <td><div py:for="lic in metadata.getLicenses()" py:content="lic"/></td>
                </tr>
                <tr class="even">
                    <td>Urls:</td>
                    <td><div py:for="url in metadata.getUrls()"><a href="${url}">${url}</a></div></td>
                </tr>
            </table>

            <hr />
            <div py:strip="True" py:if="troves[0].getName().endswith(':source')">
                ${sourceTroveInfo(troves[0])}
                <p><a href="files?t=${quote(troveName)};v=${quote(str(troves[0].getVersion()))};f=${quote(troves[0].getFlavor().freeze())}">Show Files</a></p>
            </div>
            <div py:strip="True" py:if="not trove.getName().endswith(':source')"
                 py:for="trove in troves">
                ${binaryTroveInfo(trove)}
                <p><a href="files?t=${quote(troveName)};v=${quote(str(trove.getVersion()))};f=${quote(trove.getFlavor().freeze())}">
                    Show ${troveName.startswith('group-') and 'Troves' or 'Files'}</a>
                </p>
            </div>
    

            <div py:strip="True" py:if="len(versionList) > 1">
                <h3>All Versions:</h3>
                <ul>
                    <li py:for="ver in versionList">
                        <a href="troveInfo?t=${quote(troveName)};v=${quote(str(ver))}"
                           py:if="ver != reqVer">${ver.asString()}</a>
                        <span py:strip="True" py:if="ver == reqVer"><b>${ver.asString()}</b> (selected)</span>
                    </li>
                </ul>
            </div>
        </div>
    </body>
</html>
