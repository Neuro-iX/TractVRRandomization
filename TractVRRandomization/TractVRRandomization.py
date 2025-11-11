# -*- coding: utf-8 -*-
"""
TractVRRandomization.py
Randomisation + plan par participant (JSON) + registry.csv
Inclut DataRoot/FilePattern/CaseFiles pour chargement auto dans TractDesktop/TractVR.
Compatible Python 3.9 (Slicer 5.x) : pas d’operator “|” dans les annotations.
"""

import os
import csv
import json
import random
from datetime import datetime
from typing import Optional, Dict, List, Tuple  # <-- IMPORTANT pour Python 3.9

import qt
import slicer
from slicer.i18n import tr as _
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
    ScriptedLoadableModuleLogic,
)
from slicer.util import VTKObservationMixin
from qt import QStandardPaths


# --------------------------
# Emplacements persistants
# --------------------------
APP_DATA_DIR = os.path.join(
    QStandardPaths.writableLocation(QStandardPaths.AppDataLocation),
    "TractVRRandomization"
)
PID_JSON_DIR = os.path.join(APP_DATA_DIR, "by-participant")
REGISTRY_CSV = os.path.join(APP_DATA_DIR, "registry.csv")
os.makedirs(PID_JSON_DIR, exist_ok=True)

REGISTRY_HEADER = [
    "CreatedAtISO", "ParticipantID",
    "Session1_Mode", "Session2_Mode",
    "Session1_TaskOrder", "Session2_TaskOrder",
    "DataRoot", "FilePattern", "HasCaseFiles"
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
        self.parent.contributors = ["Tina N. H. N."]
        self.parent.helpText = _(
            "Génère des plans randomisés par participant (Desktop/VR), "
            "sauvegarde un JSON, maintient un registre CSV, et peut renseigner "
            "DataRoot/FilePattern/CaseFiles pour chargement automatique des fibres."
        )
        self.parent.acknowledgementText = _("Merci à 3D Slicer / Kitware / ÉTS")


# ==========================================================
# Widget (GUI branchée sur ton .ui)
# ==========================================================
class TractVRRandomizationWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        VTKObservationMixin.__init__(self)
        self.logic = None
        self.ui = None

    # ---------- Helpers UI compatibles Qt ----------
    def _ask_text(self, title, label, default=""):
        """Retourne (text, ok) de manière robuste selon bindings Qt."""
        out = qt.QInputDialog.getText(slicer.util.mainWindow(), title, label, qt.QLineEdit.Normal, default)
        if isinstance(out, tuple):
            # (str, ok)
            if len(out) >= 2:
                return str(out[0]), bool(out[1])
            return str(out[0]), True
        # PySide peut renvoyer juste un str (rare) -> on considère ok=True si non vide
        return str(out), True if out else False

    def _ask_multiline(self, title, label, default=""):
        """Retourne (text, ok) pour getMultiLineText sans se tromper de signature."""
        out = qt.QInputDialog.getMultiLineText(slicer.util.mainWindow(), title, label, default)
        if isinstance(out, tuple):
            # (str, ok)
            if len(out) >= 2:
                return str(out[0]), bool(out[1])
            return str(out[0]), True
        return str(out), True if out else False

    def _choose_dir(self, start_dir=""):
        dlg = qt.QFileDialog(slicer.util.mainWindow(), "Choisir un dossier de données")
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
        """Charge le .ui et connecte les boutons."""
        super().setup()

        uiWidget = slicer.util.loadUI(self.resourcePath("UI/TractVRRandomization.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)
        uiWidget.setMRMLScene(slicer.mrmlScene)

        self.logic = TractVRRandomizationLogic()

        # Boutons (assignButton obligatoire)
        if not hasattr(self.ui, "assignButton"):
            raise RuntimeError("Ton .ui doit contenir un bouton 'assignButton' (ObjectName).")
        self.ui.assignButton.clicked.connect(self.onAssignParticipant)

        if hasattr(self.ui, "openFolderButton"):
            self.ui.openFolderButton.clicked.connect(self.onOpenFolder)

        if hasattr(self.ui, "browseDataRootButton"):
            self.ui.browseDataRootButton.clicked.connect(self.onBrowseDataRoot)

        self._log(f"Dossier AppData : {APP_DATA_DIR}")
        self._ensure_registry_header()
        d, v = self.logic.count_balance_session1()
        self._log(f"Équilibrage actuel Session 1 → Desktop: {d} / VR: {v}")

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
            self._log("Registre créé (nouveau).")

    def onOpenFolder(self):
        qt.QDesktopServices.openUrl(qt.QUrl.fromLocalFile(APP_DATA_DIR))

    def onBrowseDataRoot(self):
        start = ""
        if hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            start = self.ui.dataRootLineEdit.text.strip()
        path = self._choose_dir(start)
        if path and hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            self.ui.dataRootLineEdit.text = path

    # ---------- Action principale : générer un plan ----------
    def onAssignParticipant(self):
        # 1) Cas
        cases: List[str] = []
        if hasattr(self.ui, "casesLineEdit") and self.ui.casesLineEdit:
            text = (self.ui.casesLineEdit.text or "").strip()
            if text:
                cases = [c.strip() for c in text.split(",") if c.strip()]

        if not cases:
            casesCsv, ok = self._ask_multiline(
                "Liste des cas",
                "Entrez les identifiants de cas (séparés par des virgules)\n"
                "ex: AF_left,AF_right,CST_left,CST_right,IFOF_left,IFOF_right",
                "AF_left,AF_right,CST_left,CST_right,IFOF_left,IFOF_right,ILF_left,ILF_right,UF_left,UF_right"
            )
            if not ok:
                return
            cases = [c.strip() for c in (casesCsv or "").split(",") if c.strip()]

        if not cases:
            slicer.util.errorDisplay("Aucun cas valide.")
            return

        # 2) ParticipantID
        pid = ""
        if hasattr(self.ui, "pidLineEdit") and self.ui.pidLineEdit:
            pid = (self.ui.pidLineEdit.text or "").strip()
        if not pid:
            pidText, ok = self._ask_text("ParticipantID (optionnel)", "Laisser vide pour auto-générer (ex: P20251110-001) :", "")
            if not ok:
                return
            pid = (pidText or "").strip()
        if not pid:
            pid = self.logic.make_participant_id()

        # 3) DataRoot / FilePattern (optionnels)
        dataRoot = ""
        if hasattr(self.ui, "dataRootLineEdit") and self.ui.dataRootLineEdit:
            dataRoot = (self.ui.dataRootLineEdit.text or "").strip()
        if not dataRoot:
            dataRoot, ok = self._ask_text("Dossier des fibres (optionnel)", "Chemin du dossier contenant les fichiers de fibres :", "")
            if not ok:
                dataRoot = ""
        filePattern = ""
        if hasattr(self.ui, "filePatternLineEdit") and self.ui.filePatternLineEdit:
            filePattern = (self.ui.filePatternLineEdit.text or "").strip()
        if not filePattern and dataRoot:
            filePattern, ok = self._ask_text("Pattern de fichier (optionnel)",
                                             "Utilise {case} comme placeholder. Ex: {case}.vtp ou {case}.vtk",
                                             "{case}.vtp")
            if not ok:
                filePattern = ""

        # 4) CaseFiles si dataRoot+pattern sont fournis
        caseFiles: Optional[Dict[str, str]] = None
        if dataRoot and filePattern:
            mapping: Dict[str, str] = {}
            for c in cases:
                p = os.path.join(dataRoot, filePattern.format(case=c))
                mapping[c] = p
            caseFiles = mapping

        # 5) Générer plan
        try:
            plan = self.logic.make_random_plan(
                cases=cases, participant_id=pid,
                data_root=dataRoot, file_pattern=filePattern,
                case_files=caseFiles
            )
        except Exception as e:
            slicer.util.errorDisplay(f"Erreur lors de la randomisation: {e}")
            return

        # 6) Feedback
        self._log(f"✅ Participant: {plan['ParticipantID']}")
        self._log(f"Session1_Mode: {plan['Session1_Mode']}")
        self._log(f"Session2_Mode: {plan['Session2_Mode']}")
        self._log(f"S1 Order: {', '.join(plan['Session1_TaskOrder'])}")
        self._log(f"S2 Order: {', '.join(plan['Session2_TaskOrder'])}")
        if plan.get("DataRoot"):
            self._log(f"DataRoot: {plan['DataRoot']}")
        if plan.get("FilePattern"):
            self._log(f"FilePattern: {plan['FilePattern']}")
        if plan.get("CaseFiles"):
            self._log("CaseFiles: défini")
        self._log(f"JSON: {os.path.join(PID_JSON_DIR, pid + '.json')}")
        self._log("Plan enregistré.\n")

        qt.QMessageBox.information(
            slicer.util.mainWindow(),
            "TractVRRandomization",
            f"Plan généré pour {pid}\n"
            f"- {plan['Session1_Mode']} : {', '.join(plan['Session1_TaskOrder'])}\n"
            f"- {plan['Session2_Mode']} : {', '.join(plan['Session2_TaskOrder'])}\n\n"
            f"Le JSON a été sauvegardé."
        )


# ==========================================================
# Logic (aucune dépendance UI)
# ==========================================================
class TractVRRandomizationLogic(ScriptedLoadableModuleLogic):
    """
    - fabrique un ParticipantID unique (par jour : PYYYYMMDD-###)
    - équilibre Session1 (Desktop/VR) via le registre
    - randomise 2 ordres de cas (S1 et S2)
    - sauvegarde JSON + ligne dans le registre
    - enregistre éventuellement DataRoot/FilePattern/CaseFiles
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

    # Équilibrage Session 1
    def count_balance_session1(self):
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

    # Plan
    def make_random_plan(self, cases: List[str], participant_id: str,
                         data_root: str = "", file_pattern: str = "",
                         case_files: Optional[Dict[str, str]] = None) -> dict:
        if not cases:
            raise ValueError("Liste de cas vide")

        s1_mode = self._choose_s1_mode_balanced()
        s2_mode = "VR" if s1_mode == "Desktop" else "Desktop"

        s1_order = list(cases); random.shuffle(s1_order)
        s2_order = list(cases); random.shuffle(s2_order)

        plan = {
            "ParticipantID": participant_id,
            "CreatedAt": datetime.now().isoformat(timespec="seconds"),
            "Session1_Mode": s1_mode,
            "Session2_Mode": s2_mode,
            "Session1_TaskOrder": s1_order,
            "Session2_TaskOrder": s2_order,
        }

        # Métadonnées pour chargement automatique
        if data_root:
            plan["DataRoot"] = data_root
        if file_pattern:
            plan["FilePattern"] = file_pattern
        if case_files:
            plan["CaseFiles"] = case_files  # dict: {caseName: absolutePath}

        # Sauvegardes
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
                "1" if plan.get("CaseFiles") else "0",
            ])
