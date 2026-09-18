/*
Reference Rig - core loader without UI

Use this file for batch validation or automated tools.
*/

global RR_ReferenceRigCore_SourceFile
global RR_ReferenceRigCore_RootDir

RR_ReferenceRigCore_SourceFile = getSourceFileName()
RR_ReferenceRigCore_RootDir = getFilenamePath RR_ReferenceRigCore_SourceFile

fileIn (RR_ReferenceRigCore_RootDir + "RigManifest.ms")
fileIn (RR_ReferenceRigCore_RootDir + "RigScanner.ms")
fileIn (RR_ReferenceRigCore_RootDir + "BipValidator.ms")
fileIn (RR_ReferenceRigCore_RootDir + "BipTransfer.ms")
fileIn (RR_ReferenceRigCore_RootDir + "MigrateReportWriter.ms")
fileIn (RR_ReferenceRigCore_RootDir + "MigrateService.ms")
fileIn (RR_ReferenceRigCore_RootDir + "ConstraintRelinker.ms")
fileIn (RR_ReferenceRigCore_RootDir + "RigUpdater.ms")
