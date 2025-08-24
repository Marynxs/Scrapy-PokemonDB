import re
import scrapy


def format_effectiveness(txt: str) -> str:
    if not txt:
        return "neutro"
    return (txt.replace("½", "pouco efetivo")
               .replace("¼", "quase não efetivo")
               .replace("0", "nulo")
               .replace("2", "super efetivo"))


class PokemonSpider(scrapy.Spider):
    name = "pokemon"
    allowed_domains = ["pokemondb.net"]
    start_urls = ["https://pokemondb.net/pokedex/all"]

    # ----------------- Utils p/ evolução -----------------
    _LV_RE = re.compile(r"\bLevel\s*(\d+)", re.I)

    @staticmethod
    def _slug_from_href(href: str) -> str:
        if not href:
            return ""
        href = href.rstrip("/")
        return href.split("/")[-1]

    @staticmethod
    def _clean_join_text(sel):
        return " ".join(t.strip() for t in sel.css("::text").getall() if t.strip())

    @classmethod
    def _parse_level_from(cls, cond_text: str):
        m = cls._LV_RE.search(cond_text or "")
        return int(m.group(1)) if m else None

    def _collect_chain_cards_and_conds(self, chain_sel, response):
        """
        Para um bloco .infocard-list-evo (com/sem splits):
        - stages: [{id, name, link, slug}] únicos
        - edges:  [{i_from, i_to, method_text, level, item, item_link}] por seta
        """
        def parse_card(card_sel):
            name = (card_sel.css("a.ent-name::text").get() or "").strip()
            href = card_sel.css("a.ent-name::attr(href)").get() or ""
            slug = self._slug_from_href(href)
            link_abs = response.urljoin(href)
            small_text = " ".join(t.strip() for t in card_sel.css("small::text, small *::text").getall() if t.strip())
            m = re.search(r"#\s*(\d+)", small_text)
            pid = m.group(1) if m else None
            return {"id": pid, "name": name, "link": link_abs, "slug": slug}

        stages_list, slug_to_index, edges = [], {}, []

        arrows = chain_sel.xpath(".//span[contains(@class,'infocard-arrow')]")
        for arrow in arrows:
            # destino: 1º card depois da seta
            dst_card = arrow.xpath("following::div[contains(@class,'infocard')][1]")
            if not dst_card:
                continue

            # origem: se dentro de split, é o card imediatamente antes do split; senão, último antes da seta
            split_anc = arrow.xpath("ancestor::span[contains(@class,'infocard-evo-split')][1]")
            if split_anc:
                src_card = split_anc.xpath("preceding-sibling::div[contains(@class,'infocard')][1]")
            else:
                src_card = arrow.xpath("preceding::div[contains(@class,'infocard')][1]")
            if not src_card:
                continue

            a = parse_card(src_card)
            b = parse_card(dst_card)
            if not a["slug"] or not b["slug"]:
                continue

            # registra índices únicos
            if a["slug"] not in slug_to_index:
                slug_to_index[a["slug"]] = len(stages_list)
                stages_list.append(a)
            if b["slug"] not in slug_to_index:
                slug_to_index[b["slug"]] = len(stages_list)
                stages_list.append(b)

            # texto da condição (remove parênteses)
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

            level = self._parse_level_from(raw)   # "Level N" -> int
            method_text = f"Level {level}" if level is not None else raw

            edges.append({
                "i_from": slug_to_index[a["slug"]],
                "i_to": slug_to_index[b["slug"]],
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



    def _build_evolution_stages(self, response, attributes):
        """
        Monta:
        - attributes['evolution_stages'] (igual antes, porém sem duplicatas)
        - attributes['evolutions']       (lista plana: uma entrada por aresta atual -> destino)
        """
        current_slug = self._slug_from_href(attributes.get("link") or response.url)

        # Agregadores do bloco "antigo" (primeira entrada do Pokemon atual)
        from_name = from_id = from_link = None
        to_names, to_ids, to_links = [], [], []
        methods, levels, items, item_links = [], [], [], []

        # Para listar estágios extras da(s) cadeia(s)
        others_by_slug = {}

        # NOVO: lista plana de evoluções (uma por aresta) e sets para deduplicar
        evolutions = []
        seen_edges_flat = set()      # (to_slug, method, level, item)
        seen_edges_lists = set()     # mesmo critério, para deduplicar nos arrays to_/method_

        for chain in response.css("div.infocard-list-evo"):
            stages, edges = self._collect_chain_cards_and_conds(chain, response)
            if not stages:
                continue

            # Estágios "outros" (para compor as linhas envolvidas)
            for s in stages:
                if s["slug"] != current_slug:
                    others_by_slug.setdefault(
                        s["slug"],
                        {"id": s["id"], "name": s["name"], "link": s["link"]}
                    )

            # Varre edges e coleta:
            for e in edges:
                a = stages[e["i_from"]]
                b = stages[e["i_to"]]

                # anterior -> atual
                if b["slug"] == current_slug and from_name is None:
                    from_name, from_id, from_link = a["name"], a["id"], a["link"]

                # atual -> destino(s)
                if a["slug"] == current_slug:
                    key = (b["slug"], e["method_text"], e["level"], e["item"])

                    # 1) lista plana (sem duplicar)
                    if key not in seen_edges_flat:
                        seen_edges_flat.add(key)
                        evolutions.append({
                            "to_id": b["id"],
                            "to_name": b["name"],
                            "to_link": b["link"],
                            "method": e["method_text"],
                            "level": e["level"],
                            "item": e["item"],
                            "item_link": e["item_link"],
                        })

                    # 2) listas agregadas do evolution_stages (sem duplicar)
                    if key not in seen_edges_lists:
                        seen_edges_lists.add(key)
                        to_names.append(b["name"])
                        to_ids.append(b["id"])
                        to_links.append(b["link"])
                        methods.append(e["method_text"])
                        levels.append(e["level"])
                        items.append(e["item"])
                        item_links.append(e["item_link"])

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

        # Demais estágios (linhas evolutivas envolvidas)
        others_list = list(others_by_slug.values())

        attributes["evolution_stages"] = [evo_entry] + others_list
        attributes["evolutions"] = evolutions  # 👈 NOVO: uma linha por evolução atual -> destino


    # ----------------- Seu fluxo original -----------------
    def parse_base_info(self, pokemon, attributes, link):
        attributes["id"] = pokemon.css("span.infocard-cell-data::text").get()
        attributes["name"] = pokemon.css("a.ent-name::text").get()
        attributes["link"] = link
        attributes["types"] = pokemon.css("td.cell-icon a::text").getall()

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

    def parse_details(self, response, attributes):
        self.parse_height_weight(response, attributes)
        self.parse_effectiveness(response, attributes)

        # <<< Novo: evolução no formato pedido >>>
        self._build_evolution_stages(response, attributes)

        # abilities mantém yield com _pending
        yield from self.parse_abilities(response, attributes)

    def parse_height_weight(self, response, attributes):
         # Pega o texto bruto como antes
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
            height_cm = round(meters * 100, 1)  # 1 casa p/ manter precisão

        if kg_match:
            weight_kg = float(kg_match.group(1))  # já está em kg

        # Mantém as mesmas chaves, mas agora em cm e kg (numéricos)
        attributes["height"] = height_cm
        attributes["weight"] = weight_kg

    def parse_effectiveness(self, response, attributes):
        types_names = response.css("table.type-table tr:nth-child(1) th a::attr(title)").getall()
        types_multipliers = [td.css("::text").get(default="").strip()
                             for td in response.css("table.type-table tr:nth-child(2) td")]
        type_effectiveness = {}
        for t, v in zip(types_names, types_multipliers):
            type_effectiveness[t] = format_effectiveness(v)
        attributes["effectiveness"] = type_effectiveness

    def parse_abilities(self, response, attributes):
        raw_abilities = response.css("th:contains('Abilities') + td a")
        ability_links = raw_abilities.css("::attr(href)").getall()
        ability_names = [n.strip() for n in raw_abilities.css("::text").getall()]
        attributes["abilties_link"] = ability_links  # mantenho a sua chave; se quiser, renomeie p/ abilities_link
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

    def parse_ability(self, response, attributes, ability_name):
        description_text = response.css("h2:contains('Effect') + p *::text").getall()
        description_text = " ".join(t.strip() for t in description_text if t.strip()) or "—"
        attributes["abilities"][ability_name] = description_text

        attributes["_pending"] -= 1
        if attributes["_pending"] <= 0:
            attributes.pop("_pending", None)
            yield attributes