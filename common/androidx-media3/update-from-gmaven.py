#!/usr/bin/python3

# Helper script for updating androidx.media3 prebuilts from maven
#
# Usage:
#   a. Initialize android environment: $ . ./build/envsetup.sh; lunch <target>
#   b. Build pom2bp and bpfmt (needed by this script): $ m pom2bp bpfmt
#       * If this fails with 'fatal error: thread exhaustion'
#         (and then an *enormous* thread dump), retry the command.
#   c. Start a new repo branch in project `prebuilts/misc`.
#   d. Update this script:
#        * Set `media3Version` to the target version
#        * Extend `downloadArtifact` calls to include new modules if needed.
#        * Extend external dependency rewrite for any new external dependencies
#          of the imported Media3 modules.
#   e. Run the script from the Android source root:
#      $ ./prebuilts/misc/common/androidx-media3/update-from-gmaven.py
#
# The script will then:
#   1. Remove the previous artifacts
#   2. Download the aars and poms into a file structure mirroring their maven
#      path
#   3. Extract the AndroidManifest from the aars into the manifests folder
#   4. Run pom2bp to generate the Android.bp
#   5. Amend Android.bp with the existing visibility targets, java version, and
#      removal of unavailable dependencies.
#
# Manual verification steps:
#   1. Build the 'leaf' imported modules (i.e. the set that ends up depending
#      on *everything* transitively), e.g.
#      $ m androidx.media3.media3-exoplayer-dash androidx.media3.media3-exoplayer androidx.media3.media3-session androidx.media3.media3-test-utils androidx.media3.media3-transformer androidx.media3.media3-ui

import os
import re
import subprocess
import sys

media3Version="1.6.0-alpha01"

mavenToBpPatternMap = {
    "androidx.media3:" : "androidx.media3.",
    }

androidBpPath = "Android.bp"
javaVersionPattern = r'java_version:\s*"[\d\.]*",'
mockWebServerUnavailableComment = """// Missing a dependency on okhttp3.mockwebserver because this package is not currently
// available in /external/. This means the parts of this library that require this
// dependency are not usable."""

def cmd(args):
   print(args)
   out = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
   if (out.returncode != 0):
      print(out.stderr.decode("utf-8"))
      sys.exit(out.returncode)
   out_string = out.stdout.decode("utf-8")
   print(out_string)
   return out_string

def chdir(path):
   print("cd %s" % path)
   os.chdir(path)

def getAndroidRoot():
   if os.path.isdir(".repo/projects"):
      return os.getcwd()
   elif 'TOP' in os.environ:
      return os.environ['TOP']
   else:
      print("Error: Run from android source root or set TOP envvar")
      sys.exit(-1)

def downloadArtifact(groupId, artifactId, version):
   """Downloads an aar, sources.jar and pom from google maven"""
   groupPath = groupId.replace('.', '/')
   artifactDirPath = os.path.join(groupPath, artifactId, version)
   artifactPath = os.path.join(artifactDirPath, "%s-%s" % (artifactId, version))
   cmd("mkdir -p " + artifactDirPath)
   # download aar
   cmd("wget -O %s.aar https://dl.google.com/dl/android/maven2/%s.aar" % (artifactPath, artifactPath))

   # extract AndroidManifest.xml from aar, into path expected by pom2bp
   manifestDir = getManifestPath("%s:%s" % (groupId,artifactId))
   cmd("mkdir -p " + manifestDir)
   cmd("unzip -o %s.aar AndroidManifest.xml -d %s" % (artifactPath, manifestDir))

   # download pom
   cmd("wget -O %s.pom https://dl.google.com/dl/android/maven2/%s.pom" % (artifactPath, artifactPath))

   # download sources.jar
   cmd("wget -O %s-sources.jar https://dl.google.com/dl/android/maven2/%s-sources.jar" % (artifactPath, artifactPath))

def downloadApk(groupId, artifactId, version):
   """Downloads an apk from google maven"""
   groupPath = groupId.replace('.', '/')
   artifactDirPath = os.path.join(groupPath, artifactId, version)
   artifactPath = os.path.join(artifactDirPath, "%s-%s" % (artifactId, version))
   cmd("mkdir -p " + artifactDirPath)
   # download apk
   cmd("wget -O %s.apk https://dl.google.com/dl/android/maven2/%s.apk" % (artifactPath, artifactPath))
   # download pom
   cmd("wget -O %s.pom https://dl.google.com/dl/android/maven2/%s.pom" % (artifactPath, artifactPath))

def getManifestPath(mavenArtifactName):
  """Get the path to the aar's manifest as generated by pom2bp."""
  manifestPath = mavenArtifactName
  for searchPattern in mavenToBpPatternMap:
    manifestPath = manifestPath.replace(searchPattern, mavenToBpPatternMap[searchPattern])
  return "manifests/%s" % manifestPath

def getJavaVersionFromAndroidBp():
  """Returns the java_version line of the Android.bp file"""
  with open(androidBpPath, 'r') as f:
      content = f.read()
  match = re.search(javaVersionPattern, content)
  return match.group(0)  # Return the entire line

def getLibraryVisibilityFromAndroidBp():
  """Returns the entire library_visibility section of the Android.bp file"""
  with open(androidBpPath, 'r') as f:
      content = f.read()
  match = re.search(r'library_visibility\s*=\s*\[([^]]*)\]', content, re.DOTALL)
  return match.group(0)  # Return the entire matched section

def fixAndroidBp(library_visibility, java_version):
  """Fixes the Android.bp file by overwriting the visibility and java_version, and removes
      unavailable mockwebserver dependency"""
  with open(androidBpPath, 'r') as f:
      build_content = f.read()
  build_content = re.sub(javaVersionPattern, java_version, build_content)
  build_content = build_content.replace(
    r'"mockwebserver",', mockWebServerUnavailableComment)
  # Find the end of the package section (the first closing curly bracket)
  package_end_index = build_content.find('}')
  # Insert the library_visibility section after the package section
  modified_build_content = (
      build_content[:package_end_index + 1]
      + '\n\n' + library_visibility
      + build_content[package_end_index + 1:]
  )
  with open(androidBpPath, 'w') as f:
      f.write(modified_build_content)

def addTagsToAndroidBpTargets(targetType, newTag):
  """Adds the specified tag to all targets of the specified type in Android.bp"""
  with open(androidBpPath, "r") as f:
      lines = f.readlines()
  modified_lines = []
  in_target = False
  for line in lines:
      if line.strip().startswith(targetType + " {"):
          in_target = True
          modified_lines.append(line)
      elif in_target and line.strip().startswith("}"):
          modified_lines.append("    " + newTag + ",\n")
          in_target = False
          modified_lines.append(line)
      else:
          modified_lines.append(line)
  with open(androidBpPath, "w") as f:
      f.writelines(modified_lines)

prebuiltDir = os.path.join(getAndroidRoot(), "prebuilts/misc/common/androidx-media3")
chdir(prebuiltDir)

libraryVisibility = getLibraryVisibilityFromAndroidBp()
javaVersion = getJavaVersionFromAndroidBp()

cmd("rm -rf androidx/media3")
cmd("rm -rf manifests")

downloadArtifact("androidx.media3", "media3-common", media3Version)
downloadArtifact("androidx.media3", "media3-container", media3Version)
downloadArtifact("androidx.media3", "media3-database", media3Version)
downloadArtifact("androidx.media3", "media3-datasource", media3Version)
downloadArtifact("androidx.media3", "media3-decoder", media3Version)
downloadArtifact("androidx.media3", "media3-effect", media3Version)
downloadArtifact("androidx.media3", "media3-exoplayer", media3Version)
downloadArtifact("androidx.media3", "media3-exoplayer-dash", media3Version)
downloadArtifact("androidx.media3", "media3-extractor", media3Version)
downloadArtifact("androidx.media3", "media3-muxer", media3Version)
downloadArtifact("androidx.media3", "media3-session", media3Version)
downloadArtifact("androidx.media3", "media3-test-utils", media3Version)
downloadArtifact("androidx.media3", "media3-transformer", media3Version)
downloadArtifact("androidx.media3", "media3-ui", media3Version)

atxRewriteStr = ""
for name in mavenToBpPatternMap:
  atxRewriteStr += "-rewrite %s=%s " % (name, mavenToBpPatternMap[name])

cmd("pom2bp " + atxRewriteStr +
    # map external maven dependencies to Android module names
    "-rewrite androidx.annotation:annotation=androidx.annotation_annotation " +
    "-rewrite androidx.annotation:annotation-experimental=androidx.annotation_annotation-experimental " +
    "-rewrite androidx.collection:collection=androidx.collection_collection " +
    "-rewrite androidx.concurrent:concurrent-futures=androidx.concurrent_concurrent-futures " +
    "-rewrite androidx.core:core=androidx.core_core " +
    "-rewrite androidx.exifinterface:exifinterface=androidx.exifinterface_exifinterface " +
    "-rewrite androidx.media:media=androidx.media_media " +
    "-rewrite androidx.recyclerview:recyclerview=androidx.recyclerview_recyclerview " +
    "-rewrite androidx.test:core=androidx.test.core " +
    "-rewrite androidx.test.ext:junit=androidx.test.ext.junit " +
    "-rewrite androidx.test.ext:truth=androidx.test.ext.truth " +
    "-rewrite com.google.guava:guava=guava " +
    "-rewrite com.google.truth:truth=truth " +
    "-rewrite com.google.truth.extensions:truth-java8-extension=truth-java8-extension " +
    "-rewrite org.mockito:mockito-core=mockito-core " +
    "-sdk-version current " +
    "-static-deps " +
    "-prepend prepend-license.txt " +
    ". > Android.bp")

fixAndroidBp(libraryVisibility, javaVersion)
addTagsToAndroidBpTargets("android_library_import", 'visibility: ["//visibility:private"]')
addTagsToAndroidBpTargets("android_library", 'visibility: library_visibility')
cmd("bpfmt -w " + androidBpPath)
