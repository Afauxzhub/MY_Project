/*
Reference Rig - loader

Run this file in 3ds Max 2020 to load all modules and open the updater UI.
*/

global RR_ReferenceRig_SourceFile
global RR_ReferenceRig_RootDir

RR_ReferenceRig_SourceFile = getSourceFileName()
RR_ReferenceRig_RootDir = getFilenamePath RR_ReferenceRig_SourceFile

fileIn (RR_ReferenceRig_RootDir + "ReferenceRigCore.ms")
fileIn (RR_ReferenceRig_RootDir + "RigUpdateUI.ms")
