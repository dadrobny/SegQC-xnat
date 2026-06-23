# SegQC-xnat
Segmentation Quality Control Pipeline for XNAT created during the BMEIS Hackathon 2026

## Team Members - Maximum of 5 people per project
- David (david.drobny@kcl.ac.uk)
- Liane
- Name 3
- Name 4
- Name 5

## Project Title

**SegQC-xnat**: Segmentation Quality Control Pipeline for XNAT

(_SQUAT: Segmentation QUality Assessment Tool?_)

## Overview

A Docker container deployable on XNAT that runs automated image segmentation, heuristic quality control, and generates a targeted report for human review.
Applied here to 3D spine/vertebra segmentation, a task with well-known failure modes: heterogeneous imaging modalities and resolutions, variable FoV, normal and pathological appearance variation, and inconsistent labelling (e.g. T13 vs. L1).
The project also serves as a practical exercise in specification driven development (https://github.com/github/spec-kit) and AI driven engineering (e.g. https://github.com/mnriem/spec-kit-aide-extension-demo).

### Extendability
Segmentation heuristics can support downstream classification tasks:
- vertebral segment (C/T/L/S),
- pathologies (e.g. compression fracture),
- implant presence (pedicle screws, rods, intervertebral cages),
- spinal shape (scoliosis)
Additional tools can be plugged in:
- registration-based template matching,
- radiomics or similar features,
- SSM's to extend feature space towards complex shape representations

### Transferability
The pipeline generalises to any application where automated segmentation has a high failure rate.

## Data

We are using the VerSe dataset as an example for vertebra segmentation.
- https://github.com/anjany/verse
- 355 CT scans with semantic vertebra segmentations
- for a subset, there are vertebral fracture gradings available (https://osf.io/4skx2/files/zy68u)

We use TotalSegmentator as a pre-trained model for vertebra segmentation
- https://github.com/wasserth/totalsegmentator
- good general purpose segmentation tool
- provides C1-5, T1-12, L1-5, and sacrum segmentations (does not accommodate variation in numbering of vertebral segments, e.g. T13)
  

## GitHub Repository

https://github.com/dadrobny/SegQC-xnat
