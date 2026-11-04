"""Point de reprise (scripts/sauvegarde.sh) : anomalie A-01 de l'audit du 28/10/2026.

Scénario rejoué : le robot a manifeste.jsonl ouvert en écriture, quelqu'un pousse un commit sur main pendant le
passage, un point de reprise a lieu, puis le robot écrit encore. Avec l'ancien script (« git pull --rebase »),
le fichier était remplacé et la ligne écrite ensuite était perdue sans erreur."""
import os, shutil, subprocess, tempfile
import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "sauvegarde.sh")
pytestmark = pytest.mark.skipif(not shutil.which("git") or not shutil.which("bash"), reason="git ou bash absent")
ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
       "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": os.devnull}


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout


def depot():
    d = tempfile.mkdtemp()
    git("init", "-q", "--bare", "-b", "main", "origin.git", cwd=d)
    git("clone", "-q", "origin.git", "robot", cwd=d)
    robot = os.path.join(d, "robot")
    git("checkout", "-q", "-b", "main", cwd=robot)
    os.makedirs(os.path.join(robot, "etat"))
    open(os.path.join(robot, "manifeste.jsonl"), "w").write('{"l":0}\n')
    open(os.path.join(robot, "etat", "statut.json"), "w").write("{}")
    git("add", ".", cwd=robot); git("commit", "-qm", "init", cwd=robot); git("push", "-q", "origin", "main", cwd=robot)
    return d, robot


def pousser_un_commit_tiers(d):
    git("clone", "-q", "origin.git", "tiers", cwd=d)
    tiers = os.path.join(d, "tiers")
    open(os.path.join(tiers, "code.py"), "w").write("x = 1\n")
    git("add", ".", cwd=tiers); git("commit", "-qm", "commit pendant le passage", cwd=tiers); git("push", "-q", "origin", "main", cwd=tiers)


def sauvegarder(robot):
    return subprocess.run(["bash", SCRIPT], cwd=robot, env=ENV, capture_output=True, text=True, timeout=120)


def distant(d, chemin):
    return git("--git-dir", os.path.join(d, "origin.git"), "show", f"main:{chemin}", cwd=d)


def test_aucune_observation_perdue_si_main_change_pendant_le_passage():
    d, robot = depot()
    m = os.path.join(robot, "manifeste.jsonl")
    with open(m, "a", encoding="utf-8") as f:            # le robot garde le fichier ouvert, comme run_collecte.passage
        f.write('{"l":1}\n'); f.flush()
        pousser_un_commit_tiers(d)
        inode = os.stat(m).st_ino
        assert sauvegarder(robot).returncode == 0
        assert os.stat(m).st_ino == inode                # le fichier du robot n'est jamais remplacé
        f.write('{"l":2}\n'); f.flush()                  # écrit APRÈS le point de reprise
    assert sauvegarder(robot).returncode == 0
    assert distant(d, "manifeste.jsonl").split() == ['{"l":0}', '{"l":1}', '{"l":2}']
    assert distant(d, "code.py") == "x = 1\n"            # le commit tiers est conservé


def test_rien_de_nouveau_pas_de_commit():
    d, robot = depot()
    avant = git("--git-dir", os.path.join(d, "origin.git"), "rev-parse", "main", cwd=d)
    assert sauvegarder(robot).returncode == 0
    assert git("--git-dir", os.path.join(d, "origin.git"), "rev-parse", "main", cwd=d) == avant


def test_echec_du_push_visible():
    d, robot = depot()
    open(os.path.join(robot, "manifeste.jsonl"), "a").write('{"l":1}\n')
    git("remote", "set-url", "origin", os.path.join(d, "inexistant.git"), cwd=robot)
    r = sauvegarder(robot)
    assert r.returncode == 1 and "ALERTE" in r.stderr    # plus jamais de « exit 0 » sur un échec


def test_dossier_manifeste_et_suppression_de_l_ancien_fichier():
    d, robot = depot()                                    # main contient l'ancien manifeste.jsonl
    os.remove(os.path.join(robot, "manifeste.jsonl"))     # découpé localement
    os.makedirs(os.path.join(robot, "manifeste", "a"))
    open(os.path.join(robot, "manifeste", "a", "p1.jsonl"), "w").write('{"l":0}\n')
    pousser_un_commit_tiers(d)
    assert sauvegarder(robot).returncode == 0
    fichiers = git("--git-dir", os.path.join(d, "origin.git"), "ls-tree", "-r", "--name-only", "main", cwd=d).split()
    assert "manifeste/a/p1.jsonl" in fichiers and "manifeste.jsonl" not in fichiers and "code.py" in fichiers
