# -*- coding: utf-8 -*-
"""
TractVRRandomization.py
Handles randomization, participant-specific planning (JSON), and registry.csv generation.
Includes DataRoot, FilePattern, and CaseFiles for automatic loading in TractDesktop_UserStudy and TractVR_UserStudy.
Compatible with Python 3.9 (Slicer 5.x)
"""

import os
import csv
import json
import random
from datetime import datetime
from typing import Optional, Dict, List, Tuple  

import qt
import slicer
from slicer.i18n import tr as _
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)
from slicer.util import VTKObservationMixin



APP_DATA_DIR = os.path.join(
    qt.QStandardPaths.writableLocation(qt.QStandardPaths.AppDataLocation),
    "TractVRRandomization"
)
PID_JSON_DIR = os.path.join(APP_DATA_DIR, "by-participant")
REGISTRY_CSV = os.path.join(APP_DATA_DIR, "registry.csv")
os.makedirs(PID_JSON_DIR, exist_ok=True)

REGISTRY_HEADER = [
    "CreatedAtISO", "ParticipantID",
    "Session1_Mode", "Session2_Mode",
    "Session1_TaskOrder", "Session2_TaskOrder",
    "DataRoot", "FilePattern", "RefPattern", "SegPattern",
    "HasCaseFiles"
]


# ==========================================================
# Module
# ==========================================================
class TractVRRandomization(ScriptedLoadableModule):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.title = _("TractVRRandomization")
        self.parent.categories = ["Utilities"]
        self.parent.dependencies = []
        self.parent.contributors = ["Tina Nantenaina (Neuro-iX lab), Sylvain Bouix (Neuro-iX lab), Jarrett Rushmore (Boston University)"]
        self.parent.helpText = _(
            "Generates randomized participant-specific plans (Desktop/VR), "
            "saves a JSON file, maintains a CSV registry, and can populate "
            "DataRoot/FilePattern/CaseFiles for automatic fiber loading."
        )
        self.parent.acknowledgementText = _("Thanks to 3D Slicer / Kitware / ÉTS")


# ==========================================================
# Widget 
# ==========================================================
class TractVRRandomizationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self.ui = None

    # ---------- Helpers UI compatibles Qt ----------
    def _ask_text(self, title, label, default=""):
        """Returns (text, ok) across different Qt bindings"""
        out = qt.QInputDialog.getText(slicer.util.mainWindow(), title, label, qt.QLineEdit.Normal, default)
        if isinstance(out, tuple):
            if len(out) >= 2:
                return str(out[0]), bool(out[1])
            return str(out[0]), True
        return str(out), True if out else False

    def _ask_multiline(self, title, label, default=""):
        """Returns (text, ok) for getMultiLineText without calling it with the wrong signature"""
        out = qt.QInputDialog.getMultiLineText(slicer.util.mainWindow(), title, label, default)
        if isinstance(out, tuple):
            if len(out) >= 2:
                return str(out[0]), bool(out[1])
            return str(out[0]), True
        return str(out), True if out else False

    def _choose_dir(self, start_dir=""):
        dlg = qt.QFileDialog(slicer.util.mainWindow(), "Select a data folder")
        dlg.setFileMode(qt.QFileDialog.Directory)
        if start_dir and os.path.isdir(start_dir):
            dlg.setDirectory(start_dir)
        if dlg.exec_():
            sel = dlg.selectedFiles()
            if sel:
                return sel[0]
        return ""

    # ---------- Setup ----------
    def setup(self) -> None:
        """Loads the .ui file and connects the buttons"""
        super().setup()

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/TractVRRandomization.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = TractVRRandomizationLogic()

        # Buttons
        if not hasattr(self.ui, "assignButton"):
            raise RuntimeError("The .ui file must contain a button called 'assignButton' (ObjectName).")
        self.ui.assignButton.clicked.connect(self.onAssignParticipant)

        if hasattr(self.ui, "openFolderButton"):
            self.ui.openFolderButton.clicked.connect(self.onOpenFolder)

        if hasattr(self.ui, "browseDataRootButton"):
            self.ui.browseDataRootButton.clicked.connect(self.onBrowseDataRoot)

        self._log(f"Folder AppData : {APP_DATA_DIR}")
        self._ensure_registry_header()
        d, v = self.logic.count_balance_session1()
        self._log(f"Current Session 1 balance -> Desktop: {d} / VR: {v}")

    def _log(self, text: str):
        if hasattr(self.ui, "statusText") and self.ui.statusText:
            try:
                self.ui.statusText.append(text)
            except Exception:
                print(text)
        else:
            print(text)

    def _ensure_registry_header(self):
        if not os.path.exists(REGISTRY_CSV):
            os.makedirs(APP_DATA_DIR, exist_ok=True)
            with open(REGISTRY_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(REGISTRY_HEADER)
            self._log("Register created (new).")

    def onOpenFolder(self):
        qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(APP_DATA_DIR))

    def onBrowseDataRoot(self):
        start = ""
        if hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            start = self.ui.dataRootLineEdit.text.strip()
        path = self._choose_dir(start)
        if path and hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            self.ui.dataRootLineEdit.text = path

    # ---------- Main action: generate a plan ----------
    def onAssignParticipant(self):
        cases: List[str] = []
        if hasattr(self.ui, "casesLineEdit") and self.ui.casesLineEdit:
            text = (self.ui.casesLineEdit.text or "").strip()
            if text:
                cases = [c.strip() for c in text.split(",") if c.strip()]

        if not cases:
            casesCsv, ok = self._ask_multiline(
                "Case list",
                "Enter the case IDs (comma-separated)\n"
                "e.g.: FiberBundle1,FiberBundle2,FiberBundle3,FiberBundle4",
                "FiberBundle1,FiberBundle2,FiberBundle3,FiberBundle4"
            )
            if not ok:
                return
            cases = [c.strip() for c in (casesCsv or "").split(",") if c.strip()]

        if len(cases) < 4:
            slicer.util.errorDisplay("You need at least 4 cases to create 6 trials (with 2 repeated cases)")
            return
        if len(cases) > 4:
            base_cases = random.sample(cases, 4)
            self._log(f"More than 4 cases were provided : 4 were randomly selected: {', '.join(base_cases)}")
        else:
            base_cases = list(cases)

        # ParticipantID
        pid = ""
        if hasattr(self.ui, "pidLineEdit") and self.ui.pidLineEdit:
            pid = (self.ui.pidLineEdit.text or "").strip()
        if not pid:
            pidText, ok = self._ask_text("ParticipantID (optional)", "Leave blank to auto-generate (ex: P20251110-001) :", "")
            if not ok:
                return
            pid = (pidText or "").strip()
        if not pid:
            pid = self.logic.make_participant_id()

        # DataRoot / FilePattern (optionals)
        dataRoot = ""
        if hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            dataRoot = (self.ui.dataRootLineEdit.text or "").strip()
        if not dataRoot:
            dataRoot, ok = self._ask_text("Fiber folder (optional)", "Path to the folder containing the fiber files :", "")
            if not ok:
                dataRoot = ""
        filePatternNoisy = ""
        if hasattr(self.ui, "filePatternLineEdit") and self.ui.filePatternLineEdit:
            filePatternNoisy = (self.ui.filePatternLineEdit.text or "").strip()
        if not filePatternNoisy and dataRoot:
            filePatternNoisy, ok = self._ask_text(
                "Fiber bundle pattern to clean (optional)",
                "Uses {case} as a placeholder. Example: {case}.vtk",
                "{case}.vtk"
            )
            if not ok:
                filePatternNoisy = ""

        refPattern = ""
        segPattern = ""

        if dataRoot:
            refPattern, ok = self._ask_text(
                "Reference fiber bundle pattern (optional)",
                "Uses {case} as a placeholder. Example: {case}_clean.vtk",
                "{case}_clean.vtk"
            )
            if not ok:
                refPattern = ""

            segPattern, ok = self._ask_text(
                "Segmentation pattern (optional)",
                "Uses {case} as a placeholder. Example: {case}_seg.seg.nrrd",
                "{case}_seg.seg.nrrd"
            )
            if not ok:
                segPattern = ""

        caseFiles: Optional[Dict[str, str]] = None
        if dataRoot and filePatternNoisy:
            mapping: Dict[str, str] = {}
            for c in base_cases:
                p = os.path.join(dataRoot, filePatternNoisy.format(case=c))
                mapping[c] = p
            caseFiles = mapping

        # Generate the plan (with the 4-to-6 constraint: 4 cases + 2 repeated cases)
        try:
            plan = self.logic.make_random_plan_with_repeats(
            base_cases=base_cases,
            participant_id=pid,
            data_root=dataRoot,
            file_pattern=filePatternNoisy,   # Fiber to clean
            ref_pattern=refPattern,          # Fiber cleaned
            seg_pattern=segPattern,          # segmentation .seg.nrrd
            case_files=caseFiles
        )
        except Exception as e:
            slicer.util.errorDisplay(f"Error during randomization: {e}")
            return

        # Feedback
        self._log(f"Participant: {plan['ParticipantID']}")
        self._log(f"BaseCases (4): {', '.join(plan['BaseCases'])}")
        self._log(f"SixCases (6): {', '.join(plan['SixCases'])}")
        self._log(f"Session1_Mode: {plan['Session1_Mode']}")
        self._log(f"Session2_Mode: {plan['Session2_Mode']}")
        self._log(f"S1 Order (6): {', '.join(plan['Session1_TaskOrder'])}")
        self._log(f"S2 Order (6): {', '.join(plan['Session2_TaskOrder'])}")
        if plan.get("DataRoot"):
            self._log(f"DataRoot: {plan['DataRoot']}")
        if plan.get("FilePattern"):
            self._log(f"FilePattern: {plan['FilePattern']}")
        if plan.get("CaseFiles"):
            self._log("CaseFiles: défini (4 cas de base)")
        self._log(f"JSON: {os.path.join(PID_JSON_DIR, plan['ParticipantID'] + '.json')}")
        self._log("Plan saved.\n")

        qt.QMessageBox.information(
            slicer.util.mainWindow(),
            "TractVRRandomization",
            f"Plan generated for {plan['ParticipantID']}\n"
            f"- BaseCases (4) : {', '.join(plan['BaseCases'])}\n"
            f"- SixCases  (6) : {', '.join(plan['SixCases'])}\n\n"
            f"- {plan['Session1_Mode']} : {', '.join(plan['Session1_TaskOrder'])}\n"
            f"- {plan['Session2_Mode']} : {', '.join(plan['Session2_TaskOrder'])}\n\n"
            f"JSON file is saved."
        )


# ==========================================================
# Logic 
# ==========================================================
class TractVRRandomizationLogic(ScriptedLoadableModuleLogic):
    """
    - generates a unique ParticipantID for the day (PYYYYMMDD-###)
    - balances Session 1 assignment (Desktop/VR) using the registry
    - randomizes two case orders (S1 and S2)
    - saves the JSON file and adds a row to the registry
    - optionally records DataRoot/FilePattern/CaseFiles
    """

    def __init__(self):
        super().__init__()
        os.makedirs(PID_JSON_DIR, exist_ok=True)
        if not os.path.exists(REGISTRY_CSV):
            with open(REGISTRY_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(REGISTRY_HEADER)

    # ID : PYYYYMMDD-###
    def make_participant_id(self) -> str:
        today = datetime.now().strftime("%Y%m%d")
        counter = 0
        if os.path.exists(REGISTRY_CSV):
            with open(REGISTRY_CSV, "r", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    pid = row.get("ParticipantID", "")
                    if pid.startswith(f"P{today}-"):
                        counter += 1
        return f"P{today}-{counter+1:03d}"

    # Session 1 balancing
    def count_balance_session1(self) -> Tuple[int, int]:
        s1d = s1v = 0
        if os.path.exists(REGISTRY_CSV):
            with open(REGISTRY_CSV, "r", encoding="utf-8") as f:
                r = csv.DictReader(f)
                for row in r:
                    m = row.get("Session1_Mode", "")
                    if m == "Desktop":
                        s1d += 1
                    elif m == "VR":
                        s1v += 1
        return s1d, s1v

    def _choose_s1_mode_balanced(self) -> str:
        s1d, s1v = self.count_balance_session1()
        if s1d < s1v:
            return "Desktop"
        if s1v < s1d:
            return "VR"
        return random.choice(["Desktop", "VR"])

    def make_random_plan_with_repeats(
        self,
        base_cases: List[str],
        participant_id: str,
        data_root: str = "",
        file_pattern: str = "",
        ref_pattern: str = "",
        seg_pattern: str = "",
        case_files: Optional[Dict[str, str]] = None
    ) -> dict:
        """
        Constraint:
        - base_cases must contain exactly 4 distinct cases (otherwise a ValueError is raised)
        - six_cases is built from base_cases + 2 repeated cases sampled without replacement (so 2 distinct cases are repeated once each)
        - Session 1 and Session 2 use the same 'six_cases', but in a different order
        """
        if len(base_cases) != 4:
            raise ValueError("base_cases must contain exactly 4 cases")

        repeats = random.sample(base_cases, 2)   # Sampled without replacement -> 2 distinct cases
        six_cases = list(base_cases) + repeats   # total = 6 

        s1_mode = self._choose_s1_mode_balanced()
        s2_mode = "VR" if s1_mode == "Desktop" else "Desktop"

        s1_order = random.sample(six_cases, k=len(six_cases))
        s2_order = random.sample(six_cases, k=len(six_cases))

        plan = {
            "ParticipantID": participant_id,
            "CreatedAt": datetime.now().isoformat(timespec="seconds"),
            "BaseCases": base_cases,   # 4 cases
            "SixCases": six_cases,     # 6 cases (4 + 2 repeated)
            "Session1_Mode": s1_mode,
            "Session2_Mode": s2_mode,
            "Session1_TaskOrder": s1_order,
            "Session2_TaskOrder": s2_order,
        }

    
        if data_root:
            plan["DataRoot"] = data_root
        if file_pattern:
            plan["FilePattern"] = file_pattern
        if ref_pattern:
            plan["RefPattern"] = ref_pattern
        if seg_pattern:
            plan["SegPattern"] = seg_pattern
        if case_files:
            plan["CaseFiles"] = case_files

        # Saving
        self._save_plan_json(plan)
        self._append_registry(plan)
        return plan

    # I/O
    def _save_plan_json(self, plan: dict):
        path = os.path.join(PID_JSON_DIR, plan["ParticipantID"] + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(plan, f, indent=2, ensure_ascii=False)

    def _append_registry(self, plan: dict):
        exists = os.path.exists(REGISTRY_CSV)
        if not exists:
            with open(REGISTRY_CSV, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f); w.writerow(REGISTRY_HEADER)
        with open(REGISTRY_CSV, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([
                plan.get("CreatedAt", ""),
                plan["ParticipantID"],
                plan["Session1_Mode"],
                plan["Session2_Mode"],
                ",".join(plan["Session1_TaskOrder"]),
                ",".join(plan["Session2_TaskOrder"]),
                plan.get("DataRoot", ""),
                plan.get("FilePattern", ""),
                plan.get("RefPattern", ""),
                plan.get("SegPattern", ""),
                "1" if plan.get("CaseFiles") else "0",
            ])