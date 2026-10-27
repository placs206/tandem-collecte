"""Estimation du pilote : hypothèses explicites, trois scénarios. Aucun chiffre ici n'est mesuré."""
SC = {
 "bas":   dict(seances_salon=10, seances_metro=8,  delib_par_seance_metro=120, docs_autres=40, part_douteux=0.10, min_par_cas=6,  tok_doc=12_000, part_ia=0.30),
 "moyen": dict(seances_salon=14, seances_metro=10, delib_par_seance_metro=200, docs_autres=70, part_douteux=0.20, min_par_cas=10, tok_doc=20_000, part_ia=0.50),
 "haut":  dict(seances_salon=20, seances_metro=12, delib_par_seance_metro=300, docs_autres=120, part_douteux=0.35, min_par_cas=15, tok_doc=30_000, part_ia=0.80),
}
# Hypothèse de prix purement illustrative (à remplacer par la grille tarifaire en vigueur) : euros par million de jetons
PRIX_ENTREE, PRIX_SORTIE = 3.0, 15.0
for nom, h in SC.items():
    docs_seance = (h["seances_salon"] + h["seances_metro"]) * 4          # ordre du jour, extrait/PV, liste, convocation
    delib = h["seances_metro"] * h["delib_par_seance_metro"]              # PDF de délibérations de la métropole
    docs = docs_seance + delib + 2 * h["docs_autres"]
    # les délibérations de la métropole sont traitées par règles (existence, numéro) : IA sur 5 % seulement
    docs_ia = (docs_seance + 2 * h["docs_autres"]) * h["part_ia"] + delib * 0.05
    tok_in = docs_ia * h["tok_doc"] * 1.5          # 1,5 lecture par pièce (certaines sont relues après modification)
    tok_out = docs_ia * 1_500
    cout = tok_in / 1e6 * PRIX_ENTREE + tok_out / 1e6 * PRIX_SORTIE
    cas_hum = (docs_seance + 2 * h["docs_autres"]) * h["part_douteux"] * 3     # ~3 questions douteuses par document douteux
    heures = cas_hum * h["min_par_cas"] / 60
    print(f"{nom:6s} docs={docs:6.0f} dont séance={docs_seance:4.0f} délib métropole={delib:5.0f} | docs IA={docs_ia:5.0f} jetons entrée={tok_in/1e6:5.1f} M sortie={tok_out/1e6:4.2f} M coût≈{cout:5.1f} € | cas à relire≈{cas_hum:4.0f} → {heures:5.1f} h ({heures/140:4.2f} mois de 1 ETP)")
