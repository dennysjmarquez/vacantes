# Parallel Search MCP — notas de instalacion y diagnostico

Fuente: `docs.parallel.ai/integrations/mcp/search-mcp` + `docs.parallel.ai/getting-started/overview`
Leido el 2026-10-07.

## 3 correcciones a lo que se dijo antes de leer los docs

1. **No hace falta API key.** Es gratis y anonimo (tier libre, modo `fast`). Lo que se dijo
   antes ("solo te faltara la API key") estaba mal: la key solo sirve para subir rate limits.
2. **`"type": "remote"` no es el campo correcto.** Los clientes usan `"type": "http"`
   (o solo `url`). Un config invalido produce exactamente el sintoma de "no pasa nada y no
   hay error".
3. **Hay un endpoint aparte para OAuth:** `/mcp-oauth`. En `/mcp` el OAuth no se anuncia, asi
   que un cliente que espere login jamas mostrara el prompt. Es una trampa clasica de "instalado
   pero mudo".

## Donde SI funciona (maquina del usuario, con salida de red normal)

```bash
# Claude Code
claude mcp add --transport http parallel-search https://search.parallel.ai/mcp
# verificar con:  /mcp   -> debe aparecer "parallel-search"

# Codex CLI
codex mcp add parallel-search --url https://search.parallel.ai/mcp
```

**Cursor** — `~/.cursor/mcp.json` o `.cursor/mcp.json`:
```json
{ "mcpServers": { "Parallel Search MCP": { "url": "https://search.parallel.ai/mcp" } } }
```

**VS Code** — `.vscode/mcp.json`:
```json
{ "servers": { "Parallel Search MCP": { "type": "http", "url": "https://search.parallel.ai/mcp" } } }
```
> Trampa documentada: el `mcp.json` de usuario vive **dentro del perfil de VS Code**, NO en
> `~/.vscode/mcp.json`. Lo que crees a mano ahi es **ignorado sin ningun error**. Abrir con
> el comando *MCP: Open User Configuration*.

**Claude Desktop** — Settings → Developer → Edit Config (via stdio con proxy local):
```json
{ "mcpServers": { "Parallel Search MCP": { "command": "npx",
  "args": ["-y", "mcp-remote", "https://search.parallel.ai/mcp"] } } }
```

## Tuning util para vacantes (query params en la URL, sin tocar headers)

```
https://search.parallel.ai/mcp?mode=fast&advanced_settings.source_policy.include_domains=ve.computrabajo.com,computejobs.com&advanced_settings.location=ve
```

- `include_domains` / `exclude_domains` → limitar a job boards concretos. **No** soportado en modo `turbo`; usar `fast`/`basic`/`advanced`.
- Si el cliente permite headers, existe `x-parallel-search-config` con JSON. Si header y URL
  definen lo mismo, **gana el param de la URL**.
- Config invalida → `HTTP 400` en el handshake MCP (falla al conectar, no al llamar la herramienta).

## Dos detalles de diseno que importan para el pipeline de vacantes

- `web_fetch` acepta **hasta 20 URLs por llamada** → el detalle de ofertas debe ir en lotes, no oferta a oferta.
- El tier anonimo recorta excerpts a ~25.000 caracteres por llamada. `full_content: true` puede
  reventar el limite. Regla: excerpts por defecto, `full_content` solo para la oferta que vas a atacar.

## Por que NO corre en el sandbox de Arena (medido, no supuesto)

| Capa | Resultado |
|---|---|
| DNS | OK — resuelve a Cloudflare |
| TLS desde bash/Node | `SSL_ERROR_SYSCALL` — el filtro de egreso corta el handshake |
| GET con las herramientas del agente | el servidor responde `Method not allowed` (esta vivo, exige POST) |
| Connector nativo de Arena | `unsupported` |

Egreso permitido aqui: `github.com`, `api.github.com`, `codeload.github.com`, `pypi.org`,
`files.pythonhosted.org`, `registry.npmjs.org`. Ningun truco de software dentro del sandbox lo
evade, porque no es un problema de cliente MCP sino de politica de red de la plataforma.

**Equivalencia funcional:** lo que trae este MCP son dos herramientas, `web_search` y `web_fetch`.
El agente de Arena ya tiene `web_search` y `fetch_page` con el mismo contrato, y la doc de Parallel
prescribe el mismo patron: *buscar para acotar candidatos, luego extraer solo esas URLs*. Es
literalmente el embudo de dos etapas de `tools/ledger.py`.
