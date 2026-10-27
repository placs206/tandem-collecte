"""Génère obligations.csv à partir de liste-obligations.md v0.2 (transcription contrôlée).
Colonnes : id, libelle, axe, module, occurrence, texte, statut, document, condition, delai
statut: calcule | information | exclu
document: pièce qui porte la preuve (sert à P47 et aux séances attendues)
condition: aucune | fait (source publique) | evenement (consigné dans une pièce publique)
"""
import csv
A1,A2,A3,A4,A5,A6,A7=("A1 Publication des actes","A2 Fonctionnement du conseil et démocratie","A3 Finances","A4 Accès aux documents et commande publique","A5 Urbanisme et habitat","A6 Environnement, risques et services publics","A7 Personnel et social")
R=[]
def add(id,lib,axe,mod,occ,txt,statut="calcule",doc="",cond="aucune",delai=""):
    R.append(dict(id=id,libelle=lib,axe=axe,module=mod,occurrence=occ,texte=txt,statut=statut,document=doc,condition=cond,delai=delai))
# --- A. publication
add("FIN-007-E","ROB et débat d'orientation : existe et publié",A3,"M3500","par exercice","CGCT L1612-26, L2312-1, L1612-35 IV, R1612-59",doc="ROB")
add("FIN-007-D","ROB : mis en ligne dans le mois suivant l'adoption",A3,"M3500","par exercice","idem",doc="ROB",delai="1 mois depuis la délibération trouvée")
add("FIN-008-E","Présentation brève et synthétique : existe et publiée",A3,"SOCLE","par exercice (BP et CFU)","CGCT L1612-35 IV, R1612-59",doc="PRESENTATION")
add("FIN-008-D","Présentation brève : mise en ligne dans le mois",A3,"SOCLE","par exercice (BP et CFU)","idem",doc="PRESENTATION",delai="1 mois depuis la délibération trouvée")
add("FIN-011-E","Rapport d'observations définitives de la CRC : existe et publié",A3,"SOCLE","par rapport","CJF L243-6",doc="CRC",cond="fait")
add("FIN-016-E","Plan de financement des opérations subventionnées : existe et publié",A3,"SOCLE","par opération","CGCT L1111-11, D1111-8",doc="PLAN_FIN",cond="fait")
add("ACT-001-E","Délibérations : au moins une est publiée",A1,"SOCLE","par séance","CGCT L2121-7, L5211-11, L2131-1 I et III, R2131-1",doc="DELIB")
add("ACT-001-T","Délibérations : toutes sont publiées",A1,"SOCLE","par séance","idem",doc="DELIB")   # DN-57 : principe aucune / certaines / toutes
add("ACT-001-M","Délibérations : aucune disparition avant 2 mois (archivage)",A1,"SOCLE","par séance","idem",doc="DELIB",delai="2 mois")
add("ACT-002-E","PV : existe et publié (séance suivante tenue)",A1,"SOCLE","par séance","CGCT L2121-15, L2121-7, L5211-1, L5211-40-2",doc="PV")
add("ACT-002-D","PV : publié dans la semaine après la séance N+1",A1,"SOCLE","par séance","idem",doc="PV",delai="1 semaine depuis N+1")
add("ACT-003-E","Liste des délibérations : existe et publiée",A1,"SOCLE","par séance","CGCT L2121-25, L5211-1, L5211-40-2",doc="LISTE")
add("OUV-005-E","Personne responsable de l'accès aux documents publiée",A4,"M10000","par document / événement","CRPA R330-2, R330-3",doc="OUV005")
add("URB-001-E","PLU : existe et publié (Géoportail)",A5,"FAIT","par document / événement","Urbanisme L153-23",doc="PLU",cond="fait")
add("URB-002-E","Carte communale : existe et publiée",A5,"FAIT","par document / événement","Urbanisme L163-7",doc="CC",cond="fait")
add("URB-003-E","SCoT : existe et publié",A5,"FAIT","par document / événement","Urbanisme L143-24, L143-28",doc="SCOT",cond="fait")
add("URB-010-E","Rapport du commissaire enquêteur : existe et publié",A5,"SOCLE","par document / événement","Env. L123-15, R123-21",doc="CE",cond="fait")
add("URB-010-M","Rapport du commissaire enquêteur : maintenu 1 an",A5,"SOCLE","par document / événement","idem",doc="CE",cond="fait",delai="1 an")
add("URB-014-E","Rapport sur l'artificialisation des sols : existe et publié",A5,"SOCLE","par document / événement","CGCT L2231-1, R2231-1",doc="ARTIF",cond="fait")
add("URB-017-E","Données de l'offre de mobilité (PAN) : existent",A5,"FAIT","par document / événement","Transports L1115-1",doc="MOBILITE",cond="fait")
add("ENV-002-E","PCAET : existe et publié",A6,"EPCI_20000","par document / événement","Env. R229-54, R229-55",doc="PCAET")
add("ENV-003-E","Bilan des émissions de gaz à effet de serre : existe",A6,"M50000","par document / événement","Env. L229-25",doc="BEGES")
add("ENV-004-E","Cartes de bruit et plan de prévention du bruit : existent et publiés",A6,"ARRETE_BRUIT","par document / événement","Env. L572-2, L572-4, L572-7, R572-7, R572-11",doc="BRUIT",cond="fait")
add("SPL-003-E","Rapport annuel prix et qualité du service des déchets",A6,"FAIT","par document / événement","CGCT L2224-17-1, D2224-1, D2224-5, L1411-13",doc="RPQS_DECHETS",cond="fait")
add("SPL-010-E","Arrêté de collecte des déchets",A6,"FAIT","par document / événement","CGCT R2224-26, R2224-27, L2131-1",doc="ARR_DECHETS",cond="fait")
add("SPL-011-E","Programme local de prévention des déchets",A6,"FAIT","par document / événement","Env. L541-15-1, R541-41-26 à 28",doc="PLPDMA",cond="fait")
add("SPL-015-E","Devis types des opérateurs funéraires",A6,"M5000","par document / événement","CGCT L2223-21-1",doc="DEVIS_FUN")
add("ACH-001-E","Avis d'appel à la concurrence",A4,"FAIT","par document / événement","Commande publique R2131-12, R2132-2",doc="MARCHE",cond="fait")
add("ACH-002-E","Avis d'attribution",A4,"FAIT","par marché","Commande publique R2183-1",doc="MARCHE",cond="fait")
add("ACH-002-D","Avis d'attribution envoyé dans les 30 jours de la signature",A4,"FAIT","par marché","idem",doc="MARCHE",cond="fait",delai="30 jours depuis la signature")
add("ACH-003-E","Données essentielles de la commande publique",A4,"FAIT","par marché","Commande publique R2196-1, R3131-1",doc="MARCHE",cond="fait")
add("ACH-003-D","Données essentielles dans les 2 mois de la notification",A4,"FAIT","par marché","idem",doc="MARCHE",cond="fait",delai="2 mois depuis la notification")
add("INT-012-E","Estimation des incidences d'une modification de périmètre",A2,"EPCI_EVT","par document / événement","CGCT L5211-39-2",doc="PERIMETRE",cond="fait")
add("URB-021-E","Bilan annuel des acquisitions et cessions : délibération publiée",A5,"M2000","par exercice","CGCT L2241-1, L2131-1",doc="DELIB")
add("RH-001-E","Rapport social unique : existe et publié",A7,"SOCLE","par année","CGFP R231-4, R231-8",doc="RSU")
add("RH-010-E","Dix rémunérations les plus élevées : publiées",A7,"M40000","par année","CGFP L716-1",doc="REMUN")
# --- B. conseil / PV
def b(id,lib,mod,occ,txt,doc,cond="aucune"): add(id,lib,A2,mod,occ,txt,doc=doc,cond=cond)
b("CS-01","Au moins une séance par trimestre","SOCLE","par trimestre","L2121-7","SEANCES")
b("CS-02","Règlement intérieur adopté dans les 6 mois de l'installation","M1000","par mandat","L2121-8","RI")
b("CS-03","RI : fréquence et règles des questions orales","M1000","par règlement","L2121-19","RI")
b("CS-04","RI et espace d'expression des conseillers hors majorité","M1000","permanent","L2121-27-1","RI")
b("CS-05","Commissions à la représentation proportionnelle","M1000_STRICT","par commission","L2121-22","DELIB_COMMISSION")
b("CS-06","Débat sur la politique générale si demande consignée","SOCLE","par demande","L2121-19","PV","evenement")
b("CS-07","Mission d'information et d'évaluation si demande publique","M20000","par demande","L2121-22-1","PV","evenement")
for i,l in enumerate(["date et heure","nom du président","membres présents ou représentés","secrétaire(s) de séance","quorum constaté","ordre du jour","délibérations adoptées","rapports au vu desquels les délibérations ont été adoptées","demandes de scrutin particulier consignées","résultat des scrutins","teneur des discussions","signature (ou mention « signé »)"],1):
    b("PV-%02d"%i,"PV : "+l,"SOCLE","par PV","L2121-15"+(", L2121-17" if i==5 else ""),"PV")
b("VS-01","Quorum atteint","SOCLE","par séance","L2121-17","PV")
b("VS-02","Pouvoirs : un seul par conseiller, 3 séances consécutives au plus","SOCLE","par séance","L2121-20","PV")
b("VS-03","Scrutin public tenu si un quart des membres l'a demandé","SOCLE","par demande","L2121-21","PV","evenement")
b("VS-04","Scrutin secret tenu si un tiers l'a demandé ou pour une nomination","SOCLE","par scrutin","L2121-21","PV","evenement")
b("VS-05","Huis clos décidé selon la procédure et mentionné au PV","SOCLE","par séance à huis clos","L2121-18","PV","evenement")
b("VS-06","Séance du CFU : président élu, maire se retire au vote","SOCLE","par séance CFU","L2121-14","PV")
b("VS-07","Délibérations de la séance : toutes signées, numérotées, par ordre de date","SOCLE","par séance","L2121-23, R2121-9","DELIB")
# --- C. information (hors calcul)
for id,lib,axe,mod in [("FIN-001","Budget primitif",A3,"SOCLE"),("FIN-002","Budget supplémentaire",A3,"SOCLE"),("FIN-006","Compte financier unique",A3,"SOCLE"),("FIN-009","États annexés aux documents budgétaires",A3,"M3500"),("URB-004","Autorisations d'urbanisme",A5,"SOCLE"),("URB-007","DIA et registre des acquisitions",A5,"SOCLE"),("URB-016","ZAC : dossiers de création et de réalisation",A5,"FAIT"),("URB-018","Désignation des candidats aux logements sociaux",A5,"SOCLE"),("URB-019","Convention d'OPAH",A5,"SOCLE"),("URB-020","Convention de projet urbain partenarial",A5,"SOCLE"),("RIS-001","DICRIM",A6,"FAIT"),("RIS-007","Repères de crues",A6,"FAIT"),("RIS-008","Plans de prévention des risques",A6,"FAIT"),("SPL-001","Rapport annuel prix et qualité du service (eau)",A6,"FAIT"),("SPL-002","Rapport annuel prix et qualité du service (assainissement)",A6,"FAIT"),("SPL-004","Rapport annuel du délégataire",A6,"FAIT"),("SPL-006","Règlement de service eau et assainissement",A6,"SOCLE"),("RH-003","Tableau des effectifs",A7,"SOCLE"),("SOC-007","Information des usagers de la restauration collective",A7,"SOCLE"),("INT-002","Rapport d'activité de l'EPCI",A2,"EPCI"),("INT-007","Rapport du conseil de développement",A2,"EPCI_50000"),("PAT-007","Avis de publicité préalable à l'occupation du domaine public",A5,"SOCLE"),("CV-01","Convocation du conseil : délai",A2,"SOCLE"),("CV-02","Convocation du conseil : contenu",A2,"SOCLE"),("CV-03","Convocation du conseil : mode",A2,"SOCLE"),("ACT-004","Arrêtés du maire",A1,"SOCLE")]:
    add(id,lib,axe,mod,"-","voir liste-obligations.md partie C",statut="information")
for id,lib in [("RH-009","Index de l'égalité professionnelle"),("URB-009","Programme local de l'habitat"),("ACH-005","Schéma de promotion des achats publics"),("INT-013","Schéma départemental de coopération intercommunale"),("OUV-001","OUV-001 documents administratifs en ligne (collectivités d'au moins 50 agents)"),("OUV-004","OUV-004 (libellé à retrouver dans la base documentaire)"),("OUV-006","OUV-006 (libellé à retrouver dans la base documentaire)")]:
    add(id,lib,"","SOCLE","-","voir liste-obligations.md partie D",statut="exclu")
with open("obligations.csv","w",newline="",encoding="utf8") as f:
    w=csv.DictWriter(f,fieldnames=list(R[0].keys()));w.writeheader();w.writerows(R)
from collections import Counter
c=Counter(r["statut"] for r in R);print(c)
print(Counter(r["axe"][:2] for r in R if r["statut"]=="calcule"))
