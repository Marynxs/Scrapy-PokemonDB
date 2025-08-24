#pip install scrapy

import re
import scrapy

# Formata as efetividades dos tipos
def format_effectiveness(txt: str) -> str:
    if not txt:
        return "neutro"
    return (txt.replace("½", "pouco efetivo")
               .replace("¼", "quase não efetivo")
               .replace("0", "nulo")
               .replace("2", "super efetivo"))

class PokemonSpokemon_ider(scrapy.Spokemon_ider):
    name = "pokemon"
    allowed_domains = ["pokemondb.net"]
    start_urls = ["https://pokemondb.net/pokedex/all"]

    # REGEX para pegar o nivel do pokemon por exemplo: (level 16) -> 16
    LV_Regex = re.compile(r"\bLevel\s*(\d+)", re.I)

    # Pega o ultimo segmento da url por exemplo https://pokemondb.net/pokedex/bulbasaur -> bulbasaur (para saber qual a proxima evolução)
    @staticmethod
    def slug_from_href(href: str) -> str:
        if not href:
            return ""
        href = href.rstrip("/")
        return href.split("/")[-1]

    # Limpa o texto retirando espaços
    @staticmethod
    def clean_join_text(sel):
        return " ".join(txt.strip() for txt in sel.css("::text").getall() if txt.strip())

    # Faz realmente a troca de (level X) -> X se não encontrar retorna none
    @classmethod
    def parse_level_from(cls, cond_text: str):
        match = cls.LV_Regex.search(cond_text or "")
        return int(match.group(1)) if match else None
    

    def parse_cards_conds(self, chain_sel, response):

        def parse_card(card_sel):
            # Extrai o nome do Pokémon
            name = (card_sel.css("a.ent-name::text").get() or "").strip()

             # Pega o href relativo do card (link para a página do Pokémon)
            href = card_sel.css("a.ent-name::attr(href)").get() or ""

            # Converte o href em slug (último segmento do path) para usar como ID
            slug = self.slug_from_href(href)

            # Constrói link absoluto
            link_abs = response.urljoin(href)

            # Coleta os textos de como exemplo "# 133" etc.
            small_text = " ".join(t.strip() for t in card_sel.css("small::text, small *::text").getall() if t.strip())

            # Tenta extrair o número do pokemon tipo "# 133"
            match = re.search(r"#\s*(\d+)", small_text)
            pokemon_id = match.group(1) if match else None

            # Retorna a estrutura canônica de um "nó" da cadeia
            return {"id": pokemon_id, "name": name, "link": link_abs, "slug": slug}

        stages_list, slug_to_index, edges = [], {}, []

        arrows = chain_sel.xpath(".//span[contains(@class,'infocard-arrow')]")
        for arrow in arrows:
            # destino: 1º card depois da seta
            destination_card = arrow.xpath("following::div[contains(@class,'infocard')][1]")
            if not destination_card:
                continue

            # origem: se dentro de split, é o card imediatamente antes do split; senão, último antes da seta
            split_anc = arrow.xpath("ancestor::span[contains(@class,'infocard-evo-split')][1]")
            if split_anc:
                source_card = split_anc.xpath("preceding-sibling::div[contains(@class,'infocard')][1]")
            else:
                source_card = arrow.xpath("preceding::div[contains(@class,'infocard')][1]")
            if not source_card:
                continue

            from_stage = parse_card(source_card)
            to_stage = parse_card(destination_card)
            if not from_stage["slug"] or not to_stage["slug"]:
                continue

            # registra índices únicos
            if from_stage["slug"] not in slug_to_index:
                slug_to_index[from_stage["slug"]] = len(stages_list)
                stages_list.append(from_stage)
            if to_stage["slug"] not in slug_to_index:
                slug_to_index[to_stage["slug"]] = len(stages_list)
                stages_list.append(to_stage)

            # remove parenteses do level ou item
            raw = (arrow.xpath("normalize-space(string(.))").get() or "").strip()
            if raw.startswith("(") and raw.endswith(")"):
                raw = raw[1:-1].strip()

            # item (se houver)
            item_name, item_link = None, None
            for a_tag in arrow.css("a"):
                href = a_tag.css("::attr(href)").get() or ""
                if "/item/" in href:
                    item_name = (a_tag.css("::text").get() or "").strip()
                    item_link = response.urljoin(href)
                    break

            level = self.parse_level_from(raw)   # "Level N" -> int
            method_text = f"Level {level}" if level is not None else raw

            edges.append({
                "i_from": slug_to_index[from_stage["slug"]],
                "i_to": slug_to_index[to_stage["slug"]],
                "method_text": method_text,
                "level": level,
                "item": item_name,
                "item_link": item_link,
            })

        # fallback: lista cards se não houver setas
        if not stages_list:
            cards = chain_sel.xpath(".//div[contains(@class,'infocard')]")
            for c in cards:
                st = parse_card(c)
                if st["slug"] and st["slug"] not in slug_to_index:
                    slug_to_index[st["slug"]] = len(stages_list)
                    stages_list.append(st)

        return stages_list, edges



    def build_evolution_stages(self, response, attributes):


        # Descobre o slug do Pokémon atual (usa attributes['link'] se existir; senão a URL da página)
        current_slug = self.slug_from_href(attributes.get("link") or response.url)


        from_name = from_id = from_link = None # quem evolui para o atual (estágio anterior)
        to_names, to_ids, to_links = [], [], [] # destinos possíveis a partir do atual
        methods, levels, items, item_links = [], [], [], [] # guardar a forma de evolução


        others_by_slug = {}


        evolutions = []
        seen_edges_flat = set()      # (to_slug, method, level, item)
        seen_edges_lists = set()     # mesmo critério, para deduplicar nos arrays to_/method_

        for chain in response.css("div.infocard-list-evo"):
            stages, edges = self.parse_cards_conds(chain, response)
            if not stages:
                continue

            # Estágios "outros" (para compor as linhas envolvidas)
            for s in stages:
                if s["slug"] != current_slug:
                    others_by_slug.setdefault(
                        s["slug"],
                        {"id": s["id"], "name": s["name"], "link": s["link"]}
                    )

            for edge in edges:
                origin_stage = stages[edge["i_from"]]
                destination_stage = stages[edge["i_to"]]

                # anterior -> atual
                if destination_stage["slug"] == current_slug and from_name is None:
                    from_name, from_id, from_link = origin_stage["name"], origin_stage["id"], origin_stage["link"]

                # atual -> destino(s)
                if origin_stage["slug"] == current_slug:
                    key = (destination_stage["slug"], edge["method_text"], edge["level"], edge["item"])


                    if key not in seen_edges_flat:
                        seen_edges_flat.add(key)
                        evolutions.append({
                            "to_id": destination_stage["id"],
                            "to_name": destination_stage["name"],
                            "to_link": destination_stage["link"],
                            "method": edge["method_text"],
                            "level": edge["level"],
                            "item": edge["item"],
                            "item_link": edge["item_link"],
                        })


                    if key not in seen_edges_lists:
                        seen_edges_lists.add(key)
                        to_names.append(destination_stage["name"])
                        to_ids.append(destination_stage["id"])
                        to_links.append(destination_stage["link"])
                        methods.append(edge["method_text"])
                        levels.append(edge["level"])
                        items.append(edge["item"])
                        item_links.append(edge["item_link"])

        # Monta a primeira entrada (o próprio Pokémon)
        evo_entry = {
            "id": attributes.get("id"),
            "name": attributes.get("name"),
            "from": from_name,
            "id_from": from_id,
            "link_from": from_link,
            "to": to_names,
            "id_to": to_ids,
            "link_to": to_links,
            "method_evolution": methods,
            "level_to": levels,
            "item_to": items,
            "item_link_to": item_links,
        }

        # Demais estágios (linhas evolutivas)
        others_list = list(others_by_slug.values())

        attributes["evolution_stages"] = [evo_entry] + others_list
        attributes["evolutions"] = evolutions 


    # Pega todas as informações basicas do pokemon
    def parse_base_info(self, pokemon, attributes, link):
        attributes["id"] = pokemon.css("span.infocard-cell-data::text").get()
        attributes["name"] = pokemon.css("a.ent-name::text").get()
        attributes["link"] = link
        attributes["types"] = pokemon.css("td.cell-icon a::text").getall()

    # Começo do parse
    def parse(self, response):
        for pokemon in response.css("table#pokedex tbody tr"):

            link = pokemon.css("a.ent-name::attr(href)").get()
            attributes = {}
            self.parse_base_info(pokemon, attributes, link)

            if link:
                yield response.follow(
                    link,
                    callback=self.parse_details,
                    cb_kwargs={"attributes": attributes}
                )
            else:
                yield attributes

    # Pega informações da segunda tela onde tem os detalhes dos pokemons
    def parse_details(self, response, attributes):

        self.parse_height_weight(response, attributes)

        self.parse_effectiveness(response, attributes)

        self.build_evolution_stages(response, attributes)

        yield from self.parse_abilities(response, attributes)

    # Pega informações sobre a altura e peso e transforma para cm e kg
    def parse_height_weight(self, response, attributes):

        # Pega o texto bruto
        raw_height = response.css("th:contains('Height') + td::text").get() or ""
        raw_weight = response.css("th:contains('Weight') + td::text").get() or ""

        # Normaliza espaços não-quebrados e similares
        raw_height = raw_height.replace("\xa0", " ").strip()
        raw_weight = raw_weight.replace("\xa0", " ").strip()

        # Extrai o primeiro número antes de "m" e "kg"
        m_match = re.search(r"([\d.]+)\s*m\b", raw_height, flags=re.I)
        kg_match = re.search(r"([\d.]+)\s*kg\b", raw_weight, flags=re.I)

        height_cm = None
        weight_kg = None

        if m_match:
            meters = float(m_match.group(1))
            height_cm = round(meters * 100, 1)

        if kg_match:
            weight_kg = float(kg_match.group(1))

        attributes["height"] = height_cm
        attributes["weight"] = weight_kg

    # Pega as efetividades e retorna quais sao os tipos efetivos e não efetivos daquele pokemon
    def parse_effectiveness(self, response, attributes):
        types_names = response.css("table.type-table tr:nth-child(1) th a::attr(title)").getall()
        types_multipliers = [td.css("::text").get(default="").strip()
                             for td in response.css("table.type-table tr:nth-child(2) td")]
        type_effectiveness = {}
        for t, v in zip(types_names, types_multipliers):
            type_effectiveness[t] = format_effectiveness(v)
        attributes["effectiveness"] = type_effectiveness

    # Pega as habilidades e entra no link delas para pegar a descrição
    def parse_abilities(self, response, attributes):
        raw_abilities = response.css("th:contains('Abilities') + td a")
        ability_links = raw_abilities.css("::attr(href)").getall()
        ability_names = [n.strip() for n in raw_abilities.css("::text").getall()]
        attributes["abilties_link"] = ability_links 
        attributes["abilities"] = {}
        attributes["_pending"] = len(ability_links)

        if attributes["_pending"] == 0:
            attributes.pop("_pending", None)
            yield attributes
            return

        for ability_name, url in zip(ability_names, ability_links):
            yield response.follow(
                url,
                callback=self.parse_ability,
                cb_kwargs={"attributes": attributes, "ability_name": ability_name},
                dont_filter=True  # processa mesmo URLs repetidas
            )

    # Pega as descrições das habilidades dos pokemons
    def parse_ability(self, response, attributes, ability_name):
        description_text = response.css("h2:contains('Effect') + p *::text").getall()
        description_text = " ".join(t.strip() for t in description_text if t.strip()) or "—"
        attributes["abilities"][ability_name] = description_text

        attributes["_pending"] -= 1
        if attributes["_pending"] <= 0:
            attributes.pop("_pending", None)
            yield attributes