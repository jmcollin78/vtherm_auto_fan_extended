# Contenu
Ce fichier contient les spécifications du plugin `vtherm_auto_fan_extended`. Ce plugin est un plugin pour l'intégration `Versatile Thermostat` qui vise à fournir une intégration de thermostat connecté pour Home Assistant.

# Problème à résoudre
Les intégrations de type `climate` dans Home Assistant possèdent des fonctions pour changer le fan mode. La liste des `fan_modes` possibles est définie par un attribut du `climate` nommé `fan_modes`.
La difficulté est que cette liste de `fan_modes` n'est pas normalisée. Certains équipements peuvent avoir cette liste de valeurs possibles :
```
fan_modes:
  - auto
  - quiet
  - low
  - medlow
  - medium
  - medhigh
  - high
  - turbo
```

d'autres :
```
fan_modes:
  - on_low
  - on_high
  - auto_low
  - auto_high
  - "off"
```

Tout est possible et ça rend la fonction d'auto-fan-mode délicate à implémenter.

Pour rappel, la fonction `auto-fan` de `VTherm` permet d'adapter automatiquement le niveau de puissance du ventilateur d'un équipement en fonction de l'écart entre la consigne et la température réelle. L'objectif étant de brasser l'air plus fort si l'écart est important afin d'optimiser la durée d'alignement de ces températures.

La version historique (codée en dur dans le cœur) reposait sur un mapping figé (`none/low/medium/high/turbo` → indices de vitesse). Ce mapping suppose que la liste `fan_modes` contient des valeurs de vitesse reconnaissables (`low`, `1`, …) ordonnées. Il échoue sur les équipements dont les `fan_modes` ne suivent pas cette convention (ex. `on_low`, `on_high`, `auto_low`, `auto_high`, `off`).

# Proposition de solution
Le principe retenu abandonne le mapping figé au profit d'un **seuil de déclenchement par `fan_mode`**, piloté par l'utilisateur. C'est l'utilisateur — qui connaît son matériel — qui déclare quel `fan_mode` correspond à quel niveau de brassage, en lui associant un écart de température à partir duquel il doit s'activer.

## Step 1 — Cœur de la fonction

### Modèle de données (entités créées par VTherm)

Pour chaque `VTherm` éligible (scope `over_climate` exposant des `fan_modes`), le plugin crée les entités suivantes :

1. **Un `number` de seuil par `fan_mode`.**
   - Nommage : `number.<vtherm>_fan_mode_threshold_<fan_mode>` (ou approchant, après slug des caractères spéciaux).
   - Représente l'écart de température (`|consigne régulée − température pièce|`) à partir duquel ce `fan_mode` devient candidat.
   - Caractéristiques : `RestoreNumber` (survit au redémarrage), `EntityCategory.CONFIG`, `min=0`, `step=0.1`, `max` raisonnable (ex. 10).
   - **Unité** : `°C` ou `°F` selon la configuration de l'utilisateur (`hass.config.units`).
   - **Convention `seuil = 0`** (ou non défini) : ce `fan_mode` **ne participe pas** à l'auto-fan (il n'est jamais choisi comme niveau d'activation). Cela évite de créer des seuils absurdes pour des modes comme `off`, `auto`, `quiet`.

2. **Un `select` « mode de repos ».**
   - Désigne le `fan_mode` à appliquer lorsque `|écart|` est **sous tous les seuils actifs** (écart faible : rien à brasser).
   - Ne liste que les `fan_modes` réellement disponibles sur l'équipement.
   - Défaut si l'utilisateur n'a rien choisi : `off` ou `auto` s'ils existent, sinon le premier `fan_mode` de la liste.

3. **Un `switch` « Activer l'auto-fan ».**
   - Active/désactive la fonction sans perdre la configuration des seuils.
   - Lorsqu'il est sur `off`, le manager n'agit plus sur le `fan_mode` du sous-jacent.

> **Deux concepts distincts, jamais encodés sur la même valeur :**
> - « **ne participe pas** » → le `number` de seuil du mode vaut `0`.
> - « **valeur de repos** » → désignée par le `select` dédié.
>
> Le seuil `0` ne signifie donc qu'**une seule** chose (« pas un niveau d'activation »). Le repos est choisi ailleurs (le `select`). Il n'y a aucune collision possible entre les deux notions.

### Initialisation des valeurs par défaut

À la **première création** des entités (avant toute restauration `RestoreNumber`), le plugin calcule des valeurs par défaut « best-effort » afin que l'auto-fan soit immédiatement fonctionnel, sans obliger l'utilisateur à sortir tous les seuils de `0`.

**1. Classer chaque `fan_mode` en deux catégories.**
   - **Non-participant** (seuil défaut = `0`) : le `fan_mode` correspond à un repos, un mode spécial ou non lié à un niveau de brassage. Détection par appartenance à la liste d'exclusion :
     ```
     off, none, auto (ou contient "auto"), sleep, night, focus, diffuse,
     dry_fan, circulate, fresh_air, on, schedule, programmed
     ```
   - **Participant** (candidat vitesse) : tous les autres `fan_modes`, pris dans l'**ordre de la liste** `fan_modes` (par convention, généralement du plus faible au plus fort).

**2. Répartir linéairement des seuils croissants** sur les `N` participants, entre une borne basse `START` et une borne haute `END` :

$$\text{seuil}_i = \text{START} + (\text{END} - \text{START}) \cdot \frac{i}{N-1}, \quad i = 0 \dots N-1$$

   - Si `N = 1` : seuil = `START`.
   - Résultat arrondi à `0.1`.
   - **Bornes selon l'unité** de l'environnement HA (`hass.config.units`) :

     | Unité | `START` | `END` |
     |---|---|---|
     | °C | 1.0 | 3.0 |
     | °F | 2.0 | 6.0 |

**3. Mode de repos par défaut** (`select`) : premier `fan_mode` trouvé dans cet ordre de priorité :
   ```
   sleep, quiet, silent, auto, min, minimum, off
   ```
   Si aucun n'existe dans la liste de l'équipement, retenir le premier `fan_mode` disponible.

**Propriétés de cette initialisation :**
- **Best-effort assumé** : l'ordre réel des vitesses n'est pas garanti par HA. La répartition suit l'ordre de la liste `fan_modes` ; il est **documenté que l'utilisateur vérifie et ajuste** ces valeurs initiales.
- **Idempotence** : les défauts ne s'appliquent qu'à la **création initiale**. Ensuite `RestoreNumber` restaure les valeurs saisies par l'utilisateur, qui ne sont **jamais** écrasées.
- **Nouveau `fan_mode` apparu** après reconfiguration matérielle : on lui applique le même calcul de défaut à sa création (plutôt que `0`).

#### Exemple d'initialisation (unité °C)

`fan_modes = [on_low, on_high, auto_low, auto_high, off]` → 2 participants (`on_low`, `on_high`), les autres exclus (`auto_*` contient `auto`, `off` exclu) :

| `fan_mode` | Catégorie | Seuil défaut |
|---|---|---|
| `on_low` | participant (0/1) | **1.0** |
| `on_high` | participant (1/1) | **3.0** |
| `auto_low` | non-participant (contient `auto`) | 0 |
| `auto_high` | non-participant (contient `auto`) | 0 |
| `off` | non-participant | 0 |
| `select` mode de repos | — | **`off`** |

`fan_modes = [auto, quiet, low, medlow, medium, medhigh, high, turbo]` → `auto` exclu, 7 participants répartis de 1.0 à 3.0 :

| `fan_mode` | Seuil défaut |
|---|---|
| `quiet` | 1.0 |
| `low` | 1.3 |
| `medlow` | 1.7 |
| `medium` | 2.0 |
| `medhigh` | 2.3 |
| `high` | 2.7 |
| `turbo` | 3.0 |

Mode de repos par défaut : **`quiet`** (premier trouvé dans l'ordre de priorité, `sleep` étant absent).

#### Liste de référence des `fan_modes` connus

Liste la plus exhaustive possible des `fan_modes` rencontrés, utile pour la détection et les tests :

```python
EXTRA_FAN_MODES = [
    # Standards HA
    "off", "auto", "low", "medium", "high", "top", "focus", "diffuse",

    # Silencieux / Nuit
    "quiet", "silent", "sleep", "night", "min", "minimum",

    # Surpuissance / Boost
    "turbo", "powerful", "strong", "jet", "max", "maximum", "boost",

    # Modes Confort & Variés
    "breeze", "natural", "wind", "eco", "econo", "3d", "3d_auto",

    # Purificateurs & VMC
    "favorite", "custom", "circulate", "fresh_air", "auto_clean", "dry_fan",

    # Thermostats US / Continu
    "on", "schedule", "programmed",

    # Aliases & Niveaux bruts
    "middle", "mid", "lowest", "highest",
    "1", "2", "3", "4", "5", "6", "7"
]
```

### Algorithme de sélection

À chaque cycle, si l'auto-fan est activé (`switch` sur `on`) :

1. Calculer l'écart `dtemp = consigne régulée − température pièce`, puis `|dtemp|`.
2. **Cohérence chaud/froid** (garde-fou réintroduit explicitement) : l'auto-fan ne pousse pas le ventilateur à contre-sens.
   - `hvac_mode == HEAT` et `dtemp < 0` (pièce déjà plus chaude que la consigne) → **repos**.
   - `hvac_mode == COOL` et `dtemp > 0` (pièce déjà plus froide que la consigne) → **repos**.
   - `hvac_mode == OFF` → **repos**.
3. Sélection du `fan_mode` : parmi les modes dont le **seuil est strictement positif**, retenir celui dont le seuil est le **plus grand parmi ceux `≤ |dtemp|`**.
4. Si **aucun** seuil actif n'est `≤ |dtemp|` (écart trop faible), appliquer le **mode de repos** (`select`).
5. N'envoyer le `fan_mode` au sous-jacent **que s'il diffère** du dernier `fan_mode` envoyé (évite le renvoi inutile).

### Exemple concret

Matériel dont `fan_modes = [on_low, on_high, auto_low, auto_high, off]`.

Configuration utilisateur :

| Entité | Valeur | Interprétation |
|---|---|---|
| `number` seuil `on_low` | 1.0 | s'active dès que l'écart atteint 1.0° |
| `number` seuil `on_high` | 2.5 | s'active dès que l'écart atteint 2.5° |
| `number` seuil `auto_low` | 0 | ne participe pas |
| `number` seuil `auto_high` | 0 | ne participe pas |
| `number` seuil `off` | 0 | ne participe pas |
| `select` mode de repos | `off` | appliqué quand l'écart est faible |

Résultat de l'algorithme :

| `\|écart\|` | Modes candidats (seuil ≤ écart) | `fan_mode` choisi |
|---|---|---|
| 0.5 | aucun | **`off`** (repos) |
| 1.8 | `on_low` (1.0) | **`on_low`** |
| 3.0 | `on_low` (1.0), `on_high` (2.5) | **`on_high`** (plus grand seuil ≤ écart) |

Le mode de repos (`off`) a lui-même un seuil à 0, ce qui est cohérent : il ne participe pas comme niveau d'activation, il *est* le plancher.

### Observabilité

Des logs à différents niveaux facilitent le debug de la fonction. En particulier, un log utilisant `write_event_log` est émis à chaque changement de `fan_mode` provoqué par le manager (activation ou retour au repos), avec la valeur de l'écart qui a motivé la décision.

### Cas limites

- **Aucun seuil défini (tous à 0)** : l'auto-fan applique en permanence le mode de repos.
- **`underlying_fan_modes` vide au démarrage** : le sous-jacent n'a pas encore publié ses `fan_modes`. Le manager retente le calcul du mapping à chaque cycle via `refresh_state` (self-heal) jusqu'à ce que la liste soit disponible.
- **`fan_mode` disparu après reconfiguration de l'équipement** : un seuil (ou le mode de repos) référence un `fan_mode` qui n'existe plus. Le manager ignore ce mode et retombe sur le repos / un mode valide, avec un log d'avertissement.
- **`select` de repos non renseigné** : appliquer le défaut (`off`/`auto` si présents, sinon premier `fan_mode`).

### Notes d'implémentation

- Le plugin ne possède actuellement aucune plateforme d'entités. Le Step 1 implique d'ajouter les plateformes `number`, `switch` et `select`, la création de ces entités par VTherm, et le **câblage manager ↔ entités** (le manager lit les seuils / le repos / l'état du switch ; les entités notifient le manager lors d'un changement de valeur).

## Step 2 — Anti-oscillation (selon retours utilisateurs)

Autour d'un seuil, deux cycles successifs peuvent faire osciller la vitesse (va-et-vient). Prévoir une **hystérésis / bande morte** : ne changer de mode que si l'écart dépasse le seuil de ±δ, ou conserver le mode courant tant que l'écart reste dans une zone tampon.

> Le recalcul étant déclenché à chaque cycle (et non à chaque changement d'état), le besoin n'est pas certain. À implémenter en fonction des retours réels des utilisateurs.

## Step 3 — Confort, contrôle avancé et intelligence

- **Forçage temporaire d'un `fan_mode`** via un **service** dédié. L'utilisateur force un `fan_mode` pour une durée **paramétrable** ; à l'expiration du délai, l'auto-fan reprend automatiquement la main.
- **Profils chaud/froid séparés** : deux jeux de seuils distincts, car on ne brasse pas de la même manière en chauffage et en climatisation.
- **Modulation horaire / mode « sleep »** : plafonner la vitesse la nuit (ou selon un preset), pour privilégier le silence nocturne.
- **`sensor` de diagnostic** (optionnel) : exposer l'écart courant, le mode calculé et le mode réellement envoyé. Non prioritaire puisque ces informations sont déjà disponibles via les custom attributes.

# Hors périmètre
- **Auto-apprentissage** des seuils à partir de l'historique : non nécessaire pour l'instant.