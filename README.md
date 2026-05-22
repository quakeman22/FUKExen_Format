# FUKExen_Format

Formato de imagem dos jogos ExEn V2 (Ideaworks3D, ~2003) — decodificado
O ExEn era uma plataforma proprietária de jogos para celular dos anos 2000, concorrente do J2ME. Os jogos rodam em arquivos .exn/.exm carregados por um simulador Windows (GENSIMU.EXE). Não existe nenhuma documentação pública sobre o formato — isso aqui é resultado de engenharia reversa do runtime.
Estrutura do arquivo .exn
Magic: NEXE (bytes 0x00–0x03)
A partir de 0x30: tabela de offsets de 4 bytes (little-endian) apontando para cada recurso. O número de entradas é calculado pela distância entre o início da tabela e o primeiro offset não-nulo.
Cada recurso tem um tipo identificado pelo primeiro byte:
0x4E — header do arquivo
0x0B — imagem
0x00 — tabela de índices interna
0x20, 0x30, 0xB0 — bytecode/animações
Formato de imagem
Os recursos de imagem são PNGs modificados com IDAT substituído por payload proprietário comprimido. O IHDR é padrão (width, height, bit_depth=4, color_type=3). A paleta vem no chunk PLTE (16 cores RGB888). Transparência via tRNS.
O IDAT usa três codecs proprietários identificados pelo nibble alto do primeiro byte:
Type 1 — compressão por tabela de símbolos com cache LRU de 32 entradas, leitura bit a bit
Type 3 — codec de blocos com tabela de 10 símbolos, decodificação por prefixo de 2 bits
Type 5 — LZ77 proprietário: tokens de 32 bits controlam 30 operações cada (bit 1 = literal, bit 0 = backreference). O campo out_len está nos bytes 9–11 do payload em little-endian
Detalhe crítico do Type 5: os nibbles 4bpp são armazenados de trás para frente no buffer — a expansão para pixels individuais deve percorrer o buffer de packed_len até 0, invertendo a ordem dentro de cada linha.
Ferramentas
Script Python open-source que renderiza todas as imagens de um .exn para PNG
