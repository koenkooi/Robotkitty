# De asset-pijplijn

Alles in `assets/` wordt hiermee uit de twee tekeningen gesneden. Niets is nagetekend: elke sprite is een echte uitsnede.

Je hebt dit alleen nodig als je een tekening vervangt, een uitsnede anders wilt hebben, of de sprites op een andere resolutie wilt. Om het spel te spelen of aan te passen hoef je hier niets mee te doen — `assets/` staat in de repo.

## Betrouwbaarheid

`build-assets.sh` eindigt in precies één regel waar je op kunt greppen:

| Regel | Betekenis |
| --- | --- |
| `BUILD-ASSETS: SUCCESS (...)` | Klaar. Bij `--check`: alles komt overeen met `assets/`. |
| `BUILD-ASSETS: FAILURE (<stap>) -- <reden>` | Gestopt bij die stap. `assets/` is niet aangeraakt. |

Elke stap wordt gecontroleerd voordat de volgende begint, en een stap die netjes afsluit maar een leeg bestand achterlaat geldt als mislukt. De losse Python-scripts hebben hun eigen `SUCCESS` / `FAILURE`-regels in dezelfde vorm.

## Draaien

```sh
tools/build-assets.sh                  # bouwt alles en zet het in assets/
tools/build-assets.sh --check          # bouwt en vergelijkt, verandert niets
tools/build-assets.sh --only hadewych  # één tekening (sigrid | hadewych)
tools/build-assets.sh --work /tmp/rk   # bewaart de tussenstappen om te kijken
```

Reken op een paar minuten: het uitsnijden gaat pixel voor pixel.

## Wat het doet

| Tekening | Stappen |
| --- | --- |
| Sigrid | `correct.py` → `rectify.py` → `extract.py` → `webres.py` |
| Hadewych | `rectify2.py` → `extract_hw.py` → `webres_hw.py` |

Hadewychs kaart is tegen zwart gefotografeerd en gelijkmatig belicht, dus die hoeft niet vlakgetrokken te worden. Sigrids kaart is uit de hand onder een lamp geschoten en wel: er zit een vignettering in en een schaduw van een hand, en `correct.py` schat het lichtveld uit een lokaal maximum — tussen de streken door is overal papier zichtbaar.

Rechttrekken verschilt ook. Bij Sigrid staat de ingetekende schermrand als vier hoekpunten in `rectify.py`. Bij Hadewych wordt de kaart gevonden: hij is het enige in beeld dat niet bijna-zwart is, en zijn vier randen worden als lijnen gefit en gesneden. De uiterste punten van het masker nemen werkte niet — de foto heeft een lichte plek in een hoek, en dan pakt hij de hoek van de fóto.

## Hoe de poezen in stukken gaan

Sigrids poes wordt met de hand getraceerd: haar armen liggen los van de romp en haar knieën vallen precies op de zoom van het rokje, dus een paar omtrekken volstaan.

Hadewychs poes niet. Zij is één vlak rood silhouet, en met de hand getrokken grenzen namen de armen een hap uit de nek en het gezicht, en de staart een stuk van de rug. Daar worden de ledematen dus **gevonden** in plaats van getekend:

1. Erodeer het silhouet met meer dan de halve breedte van een ledemaat, maar minder dan de halve breedte van het lijf. Wat overblijft is de kern: romp en kop.
2. Dilateer die kern terug en trek hem van het silhouet af. Wat overblijft zijn de ledematen, elk afgesneden precies waar hij aan het lijf vastzit.
3. De straal wordt gezocht, niet geraden: hij moet exact vijf losse stukken opleveren.
4. Benoemen gaat op plaats — de twee laagste zijn de poten, de twee hoogste daarna de armen, en wat overblijft is de staart.
5. Het scharnier is het midden van de naad: waar het ledemaat de kern raakt.

Elk ledemaat loopt daarna een stuk de romp in en de romp een stuk het ledemaat in. Zonder die overlap raken twee uitgevaagde randen elkaar precies, en is geen van beide daar helemaal dekkend — bij een vlak rood poesje leest dat als een streep dwars over de schouders.

De staart gaat daarna nog een stap verder: die wordt in vier schakels geknipt langs zijn eigen lengte. De afstand wordt dwars dóór de vorm gemeten en niet rechtdoor, zodat een staart die terugkrult toch in gelijke stukken langs de krul wordt verdeeld in plaats van door een rechte lijn doorgesneden.

`extract_hw.py` drukt bij elke run het canvas en alle scharnieren af. Die horen in `HW` bovenin `game.js`; verandert het uitsnijvak, dan verschuiven ze allemaal.

## De achtergrond

De strepen van Hadewych worden niet gerepareerd maar opnieuw **geschilderd**. Ze lopen onder 45 graden, dus de kleur hangt alleen van `x + y` af. Elke schone streeppixel op de kaart — alles wat geen poes, kop, bloem, inkt of balk is — wordt op die as gevouwen. Dat middelt duizenden pixels per fase samen en levert één periode om uit te schilderen.

De periode wordt gezocht, niet geraden: vouwen bij elke kandidaat en die met het meeste contrast winnen. Een verkeerde periode middelt een groene baan in een paarse, dus contrast meet direct of hij klopt. Let op de ondergrens en de bovengrens van dat bereik: deze banen zijn **breed** (746px), en een zoekbereik dat bij 420 ophield koos een onzinnige smalle periode die groen en paars tot modder mengde.

Daarna wordt het profiel op zijn twee baankleuren gezet, met een paar pixels overgang aan elke rand. Middelen over de hele kaart geeft de kleuren goed maar maakt de randen zacht, want geen enkele baan is met de hand precies recht geschilderd; de tekening heeft juist vlak groen en vlak paars die op een lijn samenkomen.

Dat levert meteen iets op wat de tekening zelf niet heeft: één doorlopend veld voor het hele scherm, waardoor de strepen boven en onder de zwarte balk op elkaar aansluiten. De aarde en de balk gaan er los bovenop.

Twee eerdere pogingen strandden. Op de plek repareren gaf vegen: de rode rand van de poes loopt zacht uit, en wat blijft staan wordt langs de streeprichting uitgesmeerd. Hele pixels klonen uit een smalle strook gaf horizontale banden, want de papierkorrel herhaalde zich om de zoveel rijen.

## Als je iets verandert

| Constante | In | Wat het is |
| --- | --- | --- |
| `QUAD` | `rectify.py` | de vier hoeken van Sigrids ingetekende schermrand |
| `KITTY`, `ARMS` | `extract.py` | omtrekken van Sigrids poes en haar armen |
| `LEG_CUT_Y`, `LEG_SPLIT_X` | `extract.py` | de knielijn op de zoom, en de scheiding tussen haar benen |
| `FACE` | `extract.py` | het vakje waar rood blijft staan (snorharen) |
| `DRAWN_GOLD`, `DRAWN_INK` | `extract.py` | de kleuren waar de klompjes naartoe gaan |
| `PANEL_Y`, `SOIL_Y`, `BAR_Y`, `FIELD_Y` | `extract_hw.py` | de banden van Hadewychs kaart |
| `BUTTONS` | `extract_hw.py` | waar de twee poezenkoppen ongeveer zitten |

## Wat je niet moet doen

- **Niet blind opnieuw draaien als het faalt.** De foutregel noemt de stap; die stap is waar het misging.
- **Niet om een gefaalde controle heen werken** door de controle weg te halen. Ze staan er omdat een half geslaagde stap (een uitsnede die leeg is, een sleutel die instort) er anders gewoon doorheen loopt.
- **Niet met de hand in `assets/` knippen.** Dat raakt kwijt hoe het gemaakt is, en de volgende run zet het terug.
- **Drempels niet verruimen om een restje weg te krijgen.** Zo is het eerder misgegaan: ruimer zetten at de poes zelf op. Pas liever de omtrek aan, of laat het opruimen aan de componentenfilter over.
- **Geen tweede build starten in dezelfde werkmap** terwijl er al een loopt.

## Verder

De opzet van het spel zelf staat in [`../README.md`](../README.md).
