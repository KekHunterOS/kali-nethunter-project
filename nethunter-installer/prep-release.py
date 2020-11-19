#!/usr/bin/env python3

##############################################################
## Script to prepare NetHunter quarterly release
##
## It parses the YAML sections of devices/devices.cfg and creates:
##
## "./build-<release>.sh": shell script to build all images
## "<outputdir>/manifest.csv": manifest file mapping image name to display name
## "<outputdir>/legacy": manifest file mapping image name to display name using legacy format
##
## Usage:
## ./prep-release.py -i <input file> -o <output directory> -r <release>
##
## E.g.:
## ./prep-release.py -i devices/devices.cfg -o /opt/re4son/NetHunter/2020.3/images -r 2020.3

import yaml # install pyyaml
import getopt, os, stat, sys

FS_SIZE = "full"
build_script = "" # Generated automatically (./build-<release>.sh)
manifest = ""     # Generated automatically (<outputdir>/manifest.csv)
old_manifest = "" # Generated automatically (<outputdir>/legacy.txt)
release = ""
outputdir = ""
qty_images = 0
qty_devices = 0

## Input:
## ------------------------------------------------------------ ##
##* - angler:
##*     model:   Nexus 6P
##*     note:
##*     images:
##*       - name:    Nexus 6P (Oreo)
##*         id:      xangler
##*         os:      oreo
##*         status:  Stable
##*         note:    "** Our preferred low end device **"
##*       - name:    Nexus 6P (LineageOS 17.1)
##*         id:      angler-los
##*         os:      ten
##*         status:  Latest
##*         note:    "** Warning: Android ten is very unstable at the moment. **"


def bail(message = "", strerror = ""):
    outstr = ""
    prog = sys.argv[0]
    if message != "":
        outstr = "\n\tError: {}".format(message)
    if strerror != "":
        outstr += "\n\tMessage: {}\n".format(strerror)
    else:
        outstr += "\n\tUsage: {} -i <input file> -o <output directory> -r <release>\n".format(prog)
    print(outstr)
    sys.exit(2)

def getargs(argv):
    global inputfile, outputdir, release

    try:
        opts, args = getopt.getopt(argv,"hi:o:r:",["inputfile=","outputdir=","release="])
    except getopt.GetoptError:
        bail("Missing arguments")
    for opt, arg in opts:
        if opt == '-h':
           bail()
        elif opt in ("-i", "--input"):
           inputfile = arg
        elif opt in ("-o", "--outdir"):
           outputdir = arg
        elif opt in ("-r", "--release"):
           release = arg
    return 0

def yaml_parse(content):
    result = ""
    lines = content.split('\n')
    for line in lines:
        if line.startswith('##*'):
            ## yaml doesn't like tabs so let's replace them with four spaces 
            result += line.replace('\t', '    ')[3:] + "\n"
    return yaml.load(result, Loader=yaml.FullLoader)

def generate_build_script(data):
    build_list = ""
    global OUTPUT_FILE, FS_SIZE, release, outputdir, qty_devices, qty_images

    ## Create script header
    build_list += "#!/bin/bash\n\n"
    build_list += "RELEASE={}\n".format(release)
    build_list += "OUT_DIR={}\n".format(outputdir)
    build_list += "\n"

    ## Add builds for NetHunter light
    build_list += "# NetHunter Light:"
    build_list += "# -----------------------------------------------\n"
    build_list += "./build.py -g arm64 -fs {} -r ${{RELEASE}} && mv *${{RELEASE}}*.zip ${{OUT_DIR}}\n".format(FS_SIZE)
    build_list += "./build.py -g armhf -fs {} -r ${{RELEASE}} && mv *${{RELEASE}}*.zip ${{OUT_DIR}}\n".format(FS_SIZE)

    build_list += "\n"
    default = ""
    # iterate over all the devices
    for element in data:
        # iterate over all the versions
        for key in element.keys():
            qty_devices += 1
            if 'images' in element[key]:
                for image in element[key]['images']:
                    qty_images += 1
                    build_list += "\n"
                    build_list += "# {}\n".format(image.get('name'))
                    build_list += "# -----------------------------------------------\n"
                    build_list += "./build.py -d {} --{} -fs {} -r ${{RELEASE}} && mv *${{RELEASE}}*.zip ${{OUT_DIR}}\n".format(image.get('id', default), image.get('os', default), FS_SIZE)

    ## Create sha files for each image
    build_list += "\n\n"
    build_list += "cd ${OUT_DIR}\n"
    build_list += "for f in `dir *-${RELEASE}-*.zip`; do sha256sum ${f} > ${f}.sha256; done\n"
    build_list += "cd -\n"
    return build_list

def generate_manifest(data):
    manifest = ""
    global FS_SIZE, release

    ## Add lines for NetHunter light
    manifest += "NetHunter Lite ARM64,nethunter-{}-generic-arm64-kalifs-{}.zip\n".format(release, FS_SIZE)
    manifest += "NetHunter Lite ARMhf,nethunter-{}-generic-armhf-kalifs-{}.zip\n".format(release, FS_SIZE)

    default = ""
    # iterate over all the devices
    for element in data:
        # iterate over all the versions
        for key in element.keys():
            if 'images' in element[key]:
                for image in element[key]['images']:
                    manifest += "{},nethunter-{}-{}-kalifs-{}.zip\n".format(image.get('name', default), release, image.get('id', default), FS_SIZE)
    return manifest

def generate_old_manifest(data):
    manifest = ""
    clean_manifest = ""
    global FS_SIZE, release

    default = ""
    # iterate over all the devices
    for element in data:
        # iterate over all the versions
        for key in element.keys():
            if 'images' in element[key]:
                for image in element[key]['images']:
                    manifest += "{{% set prettyName = prettyName|regex_replace('{}','{}') %}}\n".format(image.get('id', default).capitalize(), element[key]['model'])
    manifest = deduplicate(manifest)
    return manifest

def deduplicate(data):
    # Remove duplicate lines
    clean_data = ""
    lines_seen = set()
    for line in data.splitlines():
        if line not in lines_seen: # not a duplicate
            clean_data += line + "\n" 
            lines_seen.add(line)
    return clean_data

def createdir(dir):
    try:
        if not os.path.exists(dir):
            os.makedirs(dir)
    except:
        bail('Directory "' + dir + 'does not exist and cannot be created')
    return 0

def readfile(file):
    try:
        with open(file) as f:
            data = f.read()
            f.close()
    except:
        bail("Cannot open input file")
    return data

def writefile(data, file):
    try:
        with open(file, 'w') as f:
            f.write(str(data))
            f.close()
    except:
        bail("Cannot write to output file" + file)
    return 0

def mkexec(file):
    # chmod 755
    try:
        os.chmod(file, 0o755)
    except Exception as e:
        error = "{}:{}".format(sys.exc_info()[0], sys.exc_info()[1])
        bail("Cannot make " + file + " executable", error)
    return 0

def main(argv):
    global inputfile, outputdir, release

    # Parse commandline arguments
    getargs(argv)

    # Assign variables 
    manifest = outputdir + "/manifest.csv"
    old_manifest = outputdir + "/legacy.txt"
    build_script = "./build-" + release + ".sh"
    data = readfile(inputfile)

    # Get data
    res = yaml_parse(data)
    build_list  = generate_build_script(res)
    manifest_list  = generate_manifest(res)
    old_manifest_list  = generate_old_manifest(res)

    # Create output directory if required
    createdir(outputdir)

    # Create release build script
    writefile(build_list, build_script)
    mkexec(build_script)

    # Create manifest file
    writefile(manifest_list, manifest)

    # Create legacy manifest file
    writefile(old_manifest_list, old_manifest)

    # Print result and exit
    print("\n")
    print('Build script "{}" created.'.format(build_script))
    print('Image directory "{}" created.'.format(outputdir))
    print('Manifest file "{}" created.'.format(manifest))
    print('Legacy manifest file "{}" created.'.format(old_manifest))
    print('Devices: {}'.format(qty_devices))
    print('Images:  {}'.format(qty_images))
    print("\n")

    exit(0)

if __name__ == "__main__":
    main(sys.argv[1:])

