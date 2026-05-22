# FUKExen_Format

# Formato de imagem dos jogos ExEn V2 (Ideaworks3D, ~2003) — Decodificado

O **ExEn** era uma plataforma proprietária de jogos para celular dos anos 2000, concorrente do J2ME. Os jogos rodam em arquivos `.exn/.exm` carregados por um simulador Windows (`GENSIMU.EXE`).

Não existe documentação pública conhecida sobre o formato. As informações abaixo são resultado de **engenharia reversa do runtime**.

---

## Estrutura do arquivo `.exn`

**Magic Header:**

```text
NEXE
```

**Localização:**
- Bytes `0x00–0x03`

### Tabela de recursos

A partir de:

```text
0x30
```

Existe uma tabela contendo offsets de **4 bytes (little-endian)** apontando para cada recurso presente no arquivo.

O número de entradas é determinado pela distância entre:

- início da tabela
- primeiro offset não nulo

---

## Tipos de recursos

Cada recurso possui um tipo identificado pelo **primeiro byte**:

| Byte | Tipo |
|--------|-------|
| `0x4E` | Header do arquivo |
| `0x0B` | Imagem |
| `0x00` | Tabela de índices interna |
| `0x20` | Bytecode / animações |
| `0x30` | Bytecode / animações |
| `0xB0` | Bytecode / animações |

---

# Formato de imagem

Os recursos de imagem utilizam **PNGs modificados**.

O chunk `IDAT` padrão foi substituído por um payload proprietário comprimido.

### IHDR

Formato padrão:

```text
width
height
bit_depth = 4
color_type = 3
```

### Paleta

As cores são armazenadas em:

```text
PLTE
```

Formato:

```text
16 cores RGB888
```

### Transparência

Utiliza o chunk:

```text
tRNS
```

---

# Codec do IDAT

O chunk `IDAT` usa **3 codecs proprietários**, identificados pelo **nibble alto do primeiro byte**.

## Type 1

Compressão baseada em:

- tabela de símbolos
- cache LRU de 32 entradas
- leitura bit a bit

---

## Type 3

Codec por blocos utilizando:

- tabela de 10 símbolos
- decodificação por prefixo de 2 bits

---

## Type 5

Implementação proprietária semelhante a LZ77.

### Estrutura

Tokens de **32 bits** controlam:

```text
30 operações por token
```

Regras:

```text
bit = 1 → literal
bit = 0 → backreference
```

O tamanho de saída (`out_len`) fica nos bytes:

```text
9–11
```

Formato:

```text
little-endian
```

---

## Detalhe crítico do Type 5

Os **nibbles 4bpp** são armazenados invertidos no buffer.

Durante a expansão dos pixels:

- percorrer o buffer de `packed_len → 0`
- inverter a ordem dentro de cada linha

Pseudo-fluxo:

```text
for i = packed_len → 0:
    inverter_nibble()
    escrever_pixel()
```

---

# Ferramentas

### Script Python Open Source

Funções:

- Extrair imagens de arquivos `.exn`
- Decodificar os codecs proprietários
- Renderizar imagens para PNG padrão

Saída:

```text
arquivo.exn
    ↓
decoder.py
    ↓
PNG
```

---

# Observações

- O formato não possui documentação oficial conhecida.
- A estrutura foi identificada por análise do runtime ExEn.
- Os codecs utilizados não são compatíveis com PNG convencional.
- O Type 5 possui comportamento específico que pode causar imagens corrompidas caso a ordem dos nibbles não seja invertida corretamente.
