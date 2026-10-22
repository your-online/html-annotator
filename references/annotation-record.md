# Annotation-record

Velden die `POST /save` (`h_save`) nu al schrijft. Schoonmaak zit in
`html_annotator/record.py` (`schoon_locator`, `schoon_refs`, `zet_ref_velden`).
Geen extra verplichte velden. Dit is documentatie van de bestaande interface,
geen nieuw schema.

| veld | wanneer |
|---|---|
| `nr`, `id`, `type`, `comment`, `target`, `createdAt`, `contentHash` | altijd |
| `selectedText`, `locator` | `type: text` |
| `refs`, `commentExpanded`, `refsIncomplete` | als er chips zijn / als markers ontbreken |
| `_rect`, `image`, `imageError`, `cropSource` (`live`/`file`), `liveCropError` | `type: region` |
| `veld`, `origineel`, `nieuw`, `diff`, `hunks` | `type: edit` |
| `attachment` | geplakte/bijgevoegde afbeelding |
| `resolved`, `resolvedAt` | na `/resolve` |

`locator`: `path`, `start`/`end` (`path`, `node`, `offset`), `nth`, `label`.
`refs[]`: `id`, `selectedText`, optioneel `locator`.
`liveCropError`: waarom de live snapshot niet gebruikt is (andere origin dan de bridge,
te groot, groter dan de viewport, Chrome-fout). Staat ook bij een behouden oudere crop;
`cropSource` zegt dan waar die vandaan kwam.
