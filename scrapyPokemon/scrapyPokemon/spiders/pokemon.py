import scrapy

def parse_effectiveness(txt: str) -> str:
    if not txt:
        return "neutro"
    txt = txt.replace("½", "pouco efetivo").replace("¼", "quase não efetivo").replace("0", "nulo").replace("2", "super efetivo")
    return txt

class PokemonSpider(scrapy.Spider):
    name = "pokemon"
    allowed_domains = ["pokemondb.net"]
    start_urls = ["https://pokemondb.net/pokedex/all"]

    def parse(self, response):
        for pokemon in response.css("table#pokedex tbody tr")[:5]:
            link = pokemon.css("a.ent-name::attr(href)").get()
            attributes = {
                "id" : pokemon.css("span.infocard-cell-data::text").get(),
                "name": pokemon.css("a.ent-name::text").get(),
                "link": link,
                "types": pokemon.css("td.cell-icon a::text").getall(),
            }

            if link:
                yield response.follow(link, callback=self.parse_details, cb_kwargs={"attributes": attributes})
            else:
                yield attributes


    def parse_details(self, response, attributes):
        attributes["height"] = response.css("th:contains('Height') + td::text").get() #se pa arrumar
        attributes["weight"] = response.css("th:contains('Weight') + td::text").get()

        types_names = response.css("table.type-table tr:nth-child(1) th a::attr(title)").getall() 
        types_multipliers = [p_type.css("::text").get(default="").strip() for p_type in response.css("table.type-table tr:nth-child(2) td")]
        
        type_effectiveness = {}

        for type, value in zip(types_names, types_multipliers):
            parsed_effectiveness = parse_effectiveness(value)
            type_effectiveness[type] = parsed_effectiveness

        attributes["effectiveness"] = type_effectiveness



        raw_abilities = response.css("th:contains('Abilities') + td a")
        link_abilities = raw_abilities.css("::attr(href)").getall()
        attributes["abilties_link"] = link_abilities
        attributes["abilities"] = {}
        abilities_names = raw_abilities.css("::text").getall()

        if link_abilities:
                for ability_name, link in zip(abilities_names,link_abilities):
                    yield response.follow(link, callback=self.parse_abilities, cb_kwargs={"attributes": attributes, "ability_name": ability_name} )
        else:
            yield attributes
        

    def parse_abilities(self,response, attributes, ability_name):
        description_text = response.css("h2:contains('Effect') + p *::text").getall() 
        description_text = " ".join([text.strip() for text in description_text if text.strip()])
        attributes["abilities"][ability_name] = description_text

        yield attributes
      


        