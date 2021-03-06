#!/usr/bin/env python
"""A simple wrapper script to call MIRA and collect its output.
"""
import os
import sys
import subprocess
import shutil
import time

#Do we need any PYTHONPATH magic?
from mira4_make_bam import make_bam

WRAPPER_VER = "0.0.1" #Keep in sync with the XML file

def stop_err(msg, err=1):
    sys.stderr.write(msg+"\n")
    sys.exit(err)


def get_version(mira_binary):
    """Run MIRA to find its version number"""
    # At the commend line I would use: mira -v | head -n 1
    # however there is some pipe error when doing that here.
    cmd = [mira_binary, "-v"]
    try:
        child = subprocess.Popen(cmd,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
    except Exception, err:
        sys.stderr.write("Error invoking command:\n%s\n\n%s\n" % (" ".join(cmd), err))
        sys.exit(1)
    ver, tmp = child.communicate()
    del child
    return ver.split("\n", 1)[0].strip()


try:
    mira_path = os.environ["MIRA4"]
except ImportError:
    stop_err("Environment variable $MIRA4 not set")
mira_binary = os.path.join(mira_path, "mira")
if not os.path.isfile(mira_binary):
    stop_err("Missing mira under $MIRA4, %r" % mira_binary)
mira_convert = os.path.join(mira_path, "miraconvert")
if not os.path.isfile(mira_convert):
    stop_err("Missing miraconvert under $MIRA4, %r" % mira_convert)

mira_ver = get_version(mira_binary)
if not mira_ver.strip().startswith("4.0"):
    stop_err("This wrapper is for MIRA V4.0, not:\n%s\n%s" % (mira_ver, mira_binary))
mira_convert_ver = get_version(mira_convert)
if not mira_convert_ver.strip().startswith("4.0"):
    stop_err("This wrapper is for MIRA V4.0, not:\n%s\n%s" % (mira_ver, mira_convert))
if "-v" in sys.argv or "--version" in sys.argv:
    print "%s, MIRA wrapper version %s" % (mira_ver, WRAPPER_VER)
    if mira_ver != mira_convert_ver:
        print "WARNING: miraconvert %s" % mira_convert_ver
    sys.exit(0)

def fix_threads(manifest):
    """Tweak the manifest to alter the number of threads."""
    try:
        threads = int(os.environ.get("GALAXY_SLOTS", "1"))
    except ValueError:
        threads = 1
    assert 1 <= threads 
    if threads == 1:
        #Nothing to do...
        return

    handle = open(manifest)
    text = handle.read()
    handle.close()

    text = text.replace(" -GE:not=1 ", " -GE:not=%i " % threads)

    handle = open(manifest, "w")
    handle.write(text)
    handle.flush()
    handle.close()

def log_manifest(manifest):
    """Write the manifest file to stderr."""
    sys.stderr.write("\n%s\nManifest file\n%s\n" % ("="*60, "="*60))
    with open(manifest) as h:
        for line in h:
            sys.stderr.write(line)
    sys.stderr.write("\n%s\nEnd of manifest\n%s\n" % ("="*60, "="*60))


def collect_output(temp, name, handle):
    """Moves files to the output filenames (global variables)."""
    n3 = (temp, name, name, name)
    f = "%s/%s_assembly/%s_d_results" % (temp, name, name)
    if not os.path.isdir(f):
        log_manifest(manifest)
        stop_err("Missing output folder")
    if not os.listdir(f):
        log_manifest(manifest)
        stop_err("Empty output folder")
    missing = []

    old_maf = "%s/%s_out.maf" % (f, name)
    if not os.path.isfile(old_maf):
        #Triggered extractLargeContigs.sh?
        old_maf = "%s/%s_LargeContigs_out.maf" % (f, name)

    #De novo or single strain mapping,
    old_fasta = "%s/%s_out.unpadded.fasta" % (f, name)
    ref_fasta = "%s/%s_out.padded.fasta" % (f, name)
    if not os.path.isfile(old_fasta):
        #Mapping (StrainX versus reference) or de novo
        old_fasta = "%s/%s_out_StrainX.unpadded.fasta" % (f, name)
        ref_fasta = "%s/%s_out_StrainX.padded.fasta" % (f, name)
    if not os.path.isfile(old_fasta):
        old_fasta = "%s/%s_out_ReferenceStrain.unpadded.fasta" % (f, name)
        ref_fasta = "%s/%s_out_ReferenceStrain.padded.fasta" % (f, name)
        

    missing = False
    for old, new in [(old_maf, out_maf),
                     (old_fasta, out_fasta)]:
        if not os.path.isfile(old):
            missing = True
        else:
            handle.write("Capturing %s\n" % old)
            shutil.move(old, new)
    if missing:
        log_manifest(manifest)
        sys.stderr.write("Contents of %r:\n" % f)
        for filename in sorted(os.listdir(f)):
            sys.stderr.write("%s\n" % filename)

    #For mapping mode, probably most people would expect a BAM file
    #using the reference FASTA file...
    msg = make_bam(mira_convert, out_maf, ref_fasta, out_bam, handle)
    if msg:
        stop_err(msg)

def clean_up(temp, name):
    folder = "%s/%s_assembly" % (temp, name)
    if os.path.isdir(folder):
        shutil.rmtree(folder)

#TODO - Run MIRA in /tmp or a configurable directory?
#Currently Galaxy puts us somewhere safe like:
#/opt/galaxy-dist/database/job_working_directory/846/
temp = "."
#name, out_fasta, out_qual, out_ace, out_caf, out_wig, out_log = sys.argv[1:8]
name = "MIRA"
manifest, out_maf, out_bam, out_fasta, out_log = sys.argv[1:]

fix_threads(manifest)

start_time = time.time()
#cmd_list =sys.argv[8:]
cmd_list = [mira_binary, manifest]
cmd = " ".join(cmd_list)

assert os.path.isdir(temp)
d = "%s_assembly" % name
assert not os.path.isdir(d), "Path %s already exists" % d
try:
    #Check path access
    os.mkdir(d)
except Exception, err:
    log_manifest(manifest)
    sys.stderr.write("Error making directory %s\n%s" % (d, err))
    sys.exit(1)

#print os.path.abspath(".")
#print cmd

handle = open(out_log, "w")
handle.write("======================== MIRA manifest (instructions) ========================\n")
m = open(manifest, "rU")
for line in m:
    handle.write(line)
m.close()
del m
handle.write("\n")
handle.write("============================ Starting MIRA now ===============================\n")
handle.flush()
try:
    #Run MIRA
    child = subprocess.Popen(cmd_list,
                             stdout=handle,
                             stderr=subprocess.STDOUT)
except Exception, err:
    log_manifest(manifest)
    sys.stderr.write("Error invoking command:\n%s\n\n%s\n" % (cmd, err))
    #TODO - call clean up?
    handle.write("Error invoking command:\n%s\n\n%s\n" % (cmd, err))
    handle.close()
    sys.exit(1)
#Use .communicate as can get deadlocks with .wait(),
stdout, stderr = child.communicate()
assert not stdout and not stderr #Should be empty as sent to handle
run_time = time.time() - start_time
return_code = child.returncode
handle.write("\n")
handle.write("============================ MIRA has finished ===============================\n")
handle.write("MIRA took %0.2f hours\n" % (run_time / 3600.0))
if return_code:
    print "MIRA took %0.2f hours" % (run_time / 3600.0)
    handle.write("Return error code %i from command:\n" % return_code)
    handle.write(cmd + "\n")
    handle.close()
    clean_up(temp, name)
    log_manifest(manifest)
    stop_err("Return error code %i from command:\n%s" % (return_code, cmd),
             return_code)
handle.flush()

if os.path.isfile("MIRA_assembly/MIRA_d_results/ec.log"):
    handle.write("\n")
    handle.write("====================== Extract Large Contigs failed ==========================\n")
    e = open("MIRA_assembly/MIRA_d_results/ec.log", "rU")
    for line in e:
        handle.write(line)
    e.close()
    handle.write("============================ (end of ec.log) =================================\n")
    handle.flush()

#print "Collecting output..."
start_time = time.time()
collect_output(temp, name, handle)
collect_time = time.time() - start_time
handle.write("MIRA took %0.2f hours; collecting output %0.2f minutes\n" % (run_time / 3600.0, collect_time / 60.0))
print("MIRA took %0.2f hours; collecting output %0.2f minutes\n" % (run_time / 3600.0, collect_time / 60.0))

if os.path.isfile("MIRA_assembly/MIRA_d_results/ec.log"):
    #Treat as an error, but doing this AFTER collect_output
    sys.stderr.write("Extract Large Contigs failed\n")
    handle.write("Extract Large Contigs failed\n")
    handle.close()
    sys.exit(1)

#print "Cleaning up..."
clean_up(temp, name)

handle.write("\nDone\n")
handle.close()
print("Done")
