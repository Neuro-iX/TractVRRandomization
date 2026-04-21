# TractVRRandomisation

## Overview
TractVRRandomisation is a utility module developed for the experimental study. Its purpose is to generate participant-specific study plans and randomize session order and case presentation.

## Repository context
This repository is part of the experimental framework. It supports the organization and preparation of the user study and is not intended for routine tractography use.

## Related repositories
- [TractVR](https://github.com/TinaNant28/TractVR) – operational VR module for routine professional use
- [TractDesktop](https://github.com/TinaNant28/TractDesktop) – operational desktop module for routine professional use
- [TractVR_UserStudy](https://github.com/TinaNant28/TractVR_UserStudy) – VR module used in the experimental study
- [TractDesktop_UserStudy](https://github.com/TinaNant28/TractDesktop_UserStudy) – desktop module used in the experimental study

## Main features
- Generation of participant-specific experimental plans
- Randomization of session order
- Randomization of case order
- Export of study configuration files
- Support for reproducible study setup

## Intended users
This module is intended for study preparation and experimental management. It is not intended for routine clinical or professional tractography use.

## Dependencies
- Python
- JSON and file management utilities
- 3D Slicer if required by the implementation
- Other required libraries if applicable

## Installation
1. Clone or download this repository.
2. Install the required environment and dependencies.
3. Configure the input data paths and file naming patterns if needed.
4. Run the randomization workflow according to the study protocol.

## Usage
1. Define the base cases and the required configuration parameters.
2. Run the randomization module.
3. Generate participant-specific plans.
4. Save the output files for later use in the experimental sessions.

## Notes
This repository is intended only for the preparation and management of the experimental study. It should be used together with the [TractVR_UserStudy](https://github.com/TinaNant28/TractVR_UserStudy) and [TractDesktop_UserStudy](https://github.com/TinaNant28/TractDesktop_UserStudy) repositories.

## Funding
This work was developed as part of a project funded by the Canada Research Chair in Neuroinformatics for Multimodal Data.  
Designated responsible investigator: Sylvain Bouix  
Reference number: CRC-2022-00183

## Acknowledgments
This module was developed as part of the experimental framework supporting the tractography user study.
