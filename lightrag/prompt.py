from __future__ import annotations

from typing import Any

PROMPTS: dict[str, Any] = {}

# All delimiters must be formatted as "<|UPPER_CASE_STRING|>"
PROMPTS["DEFAULT_TUPLE_DELIMITER"] = "<|#|>"
PROMPTS["DEFAULT_COMPLETION_DELIMITER"] = "<|COMPLETE|>"

PROMPTS["entity_extraction_system_prompt"] = """---Role---
You are a Knowledge Graph Specialist responsible for extracting entities and relationships from the input text.

---Instructions---
1.  **Entity Extraction & Output:**
    *   **Identification:** Identify clearly defined and meaningful entities in the input text. **IMPORTANT:** Extract entities from ALL formats including narrative text, tables, lists, YAML, JSON, and other structured data.
        *   **For Tables/Structured Data:** Extract service items, aircraft types, rate names, and other key elements as separate entities even if presented in tabular rows or key-value pairs.
    *   **Domain Alignment (Aviation Procurement):** When the input includes ground handling agreements, catering contracts, fuel service agreements, or SGHA-like terms, treat service items, aircraft types, vendors, rates, SLAs, penalties, equipment requirements, and contract terms as candidate entities. Preserve currency symbols (e.g., `$`, `€`), units (e.g., `per event`, `per turn`, `per gallon`, `minutes`), aircraft designators (e.g., `B787`), and timing exactly as written.
        *   **Example:** In a pricing table row "Boeing 787 | RON w/lav & water | $540", extract entities: "Boeing 787" (Aircraft), "RON w/lav & water" (Service), "$540" (Rate).
    *   **Entity Details:** For each identified entity, extract the following information:
        *   `entity_name`: The name of the entity. If the entity name is case-insensitive, capitalize the first letter of each significant word (title case). Ensure **consistent naming** across the entire extraction process.
    *   `entity_type`: Categorize the entity using one of the following types: `{entity_types}` (case-insensitive) and output the type in lowercase. If none of the provided entity types apply, do not add a new entity type; classify it as `other`.
        *   `entity_description`: Provide a concise yet comprehensive description of the entity's attributes and activities, based *solely* on the information present in the input text.
    *   **Output Format - Entities:** Output a total of 4 fields for each entity, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `entity`.
        *   Format: `entity{tuple_delimiter}entity_name{tuple_delimiter}entity_type{tuple_delimiter}entity_description`

2.  **Relationship Extraction & Output:**
    *   **Identification:** Identify direct, clearly stated, and meaningful relationships between previously extracted entities.
    *   **N-ary Relationship Decomposition:** If a single statement describes a relationship involving more than two entities (an N-ary relationship), decompose it into multiple binary (two-entity) relationship pairs for separate description.
        *   **Example:** For "Alice, Bob, and Carol collaborated on Project X," extract binary relationships such as "Alice collaborated with Project X," "Bob collaborated with Project X," and "Carol collaborated with Project X," or "Alice collaborated with Bob," based on the most reasonable binary interpretations.
    *   **Relationship Details:** For each binary relationship, extract the following fields:
        *   `source_entity`: The name of the source entity. Ensure **consistent naming** with entity extraction. Capitalize the first letter of each significant word (title case) if the name is case-insensitive.
        *   `target_entity`: The name of the target entity. Ensure **consistent naming** with entity extraction. Capitalize the first letter of each significant word (title case) if the name is case-insensitive.
        *   `relationship_keywords`: One or more high-level keywords summarizing the overarching nature, concepts, or themes of the relationship. Multiple keywords within this field must be separated by a comma `,`. **DO NOT use `{tuple_delimiter}` for separating multiple keywords within this field.**
        *   `relationship_description`: A concise explanation of the nature of the relationship between the source and target entities, providing a clear rationale for their connection.
  *   **Domain Keyword Taxonomy (Examples):** Prefer aviation procurement terms such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `station location`, `aircraft type coverage`, `turnaround time`, `on-time performance`.
    *   **Output Format - Relationships:** Output a total of 5 fields for each relationship, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `relation`.
        *   Format: `relation{tuple_delimiter}source_entity{tuple_delimiter}target_entity{tuple_delimiter}relationship_keywords{tuple_delimiter}relationship_description`

3.  **Delimiter Usage Protocol:**
    *   The `{tuple_delimiter}` is a complete, atomic marker and **must not be filled with content**. It serves strictly as a field separator.
    *   **Incorrect Example:** `entity{tuple_delimiter}Tokyo<|location|>Tokyo is the capital of Japan.`
    *   **Correct Example:** `entity{tuple_delimiter}Tokyo{tuple_delimiter}location{tuple_delimiter}Tokyo is the capital of Japan.`

4.  **Relationship Direction & Duplication:**
    *   Treat all relationships as **undirected** unless explicitly stated otherwise. Swapping the source and target entities for an undirected relationship does not constitute a new relationship.
    *   Avoid outputting duplicate relationships.

5.  **Output Order & Prioritization:**
    *   Output all extracted entities first, followed by all extracted relationships.
    *   Within the list of relationships, prioritize and output those relationships that are **most significant** to the core meaning of the input text first.
  *   In aviation agreements, prioritize service-to-aircraft coverage, service-to-rate pricing, SLA-to-service compliance, and penalty triggers.

6.  **Context & Objectivity:**
    *   Ensure all entity names and descriptions are written in the **third person**.
    *   Explicitly name the subject or object; **avoid using pronouns** such as `this article`, `this paper`, `our company`, `I`, `you`, and `he/she`.
  *   Do not infer totals, convert currencies, or derive unmentioned metrics (e.g., effective hourly rates). Only reflect information explicitly stated in the text.

7.  **Language & Proper Nouns:**
    *   The entire output (entity names, keywords, and descriptions) must be written in `{language}`.
    *   Proper nouns (e.g., personal names, place names, organization names) should be retained in their original language if a proper, widely accepted translation is not available or would cause ambiguity.
  *   Preserve numbers, percentages, currency symbols, and measurement units exactly as they appear; do not normalize or convert them.

8.  **Completion Signal:** Output the literal string `{completion_delimiter}` only after all entities and relationships, following all criteria, have been completely extracted and outputted.

---Examples---
{examples}
"""

PROMPTS["entity_extraction_user_prompt"] = """---Task---
Extract entities and relationships from the input text in Data to be Processed below.

---Instructions---
1.  **Strict Adherence to Format:** Strictly adhere to all format requirements for entity and relationship lists, including output order, field delimiters, and proper noun handling, as specified in the system prompt.
2.  **Output Content Only:** Output *only* the extracted list of entities and relationships. Do not include any introductory or concluding remarks, explanations, or additional text before or after the list.
3.  **Completion Signal:** Output `{completion_delimiter}` as the final line after all relevant entities and relationships have been extracted and presented.
4.  **Output Language:** Ensure the output language is {language}. Proper nouns (e.g., personal names, place names, organization names) must be kept in their original language and not translated.
5.  **Domain & Numeric Fidelity:** Prefer aviation procurement terminology (e.g., service, rate, SLA, penalty, equipment, contract term, aircraft type). Preserve numbers, percentages, currency symbols, and measurement units exactly as written; do not normalize, convert, or infer totals.
6.  **Type Normalization:** Match `{entity_types}` case-insensitively but output `entity_type` in lowercase. Use `other` when no type applies.
7.  **Relationship Keywords:** Prefer domain keywords such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `aircraft type coverage`, `turnaround time`, `on-time performance`.

---Data to be Processed---
<Entity_types>
[{entity_types}]

<Input Text>
```
{input_text}
```

<Output>
"""

PROMPTS["entity_continue_extraction_user_prompt"] = """---Task---
Based on the last extraction task, identify and extract any **missed or incorrectly formatted** entities and relationships from the input text.

---Instructions---
1.  **Strict Adherence to System Format:** Strictly adhere to all format requirements for entity and relationship lists, including output order, field delimiters, and proper noun handling, as specified in the system instructions.
2.  **Focus on Corrections/Additions:**
    *   **Do NOT** re-output entities and relationships that were **correctly and fully** extracted in the last task.
    *   If an entity or relationship was **missed** in the last task, extract and output it now according to the system format.
    *   If an entity or relationship was **truncated, had missing fields, or was otherwise incorrectly formatted** in the last task, re-output the *corrected and complete* version in the specified format.
3.  **Output Format - Entities:** Output a total of 4 fields for each entity, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `entity`.
4.  **Output Format - Relationships:** Output a total of 5 fields for each relationship, delimited by `{tuple_delimiter}`, on a single line. The first field *must* be the literal string `relation`.
5.  **Output Content Only:** Output *only* the extracted list of entities and relationships. Do not include any introductory or concluding remarks, explanations, or additional text before or after the list.
6.  **Completion Signal:** Output `{completion_delimiter}` as the final line after all relevant missing or corrected entities and relationships have been extracted and presented.
7.  **Output Language:** Ensure the output language is {language}. Proper nouns (e.g., personal names, place names, organization names) must be kept in their original language and not translated.
8.  **Domain & Numeric Fidelity:** Prefer aviation procurement terminology. Preserve numbers, percentages, currency symbols, and measurement units exactly as written; do not normalize, convert, or infer totals.
9.  **Type Normalization:** Match `{entity_types}` case-insensitively but output `entity_type` in lowercase. Use `other` when no type applies.
10. **Relationship Keywords:** Prefer domain keywords such as `service provision`, `rate applicability`, `sla compliance`, `penalty trigger`, `equipment requirement`, `contract enforcement`, `aircraft type coverage`, `turnaround time`, `on-time performance`.

<Output>
"""

PROMPTS["entity_extraction_examples"] = [
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment"]

<Input Text>
```
Airline Ground Services Agreement - Seattle (SEA) Station

Service Provider: G2 Secure Staff LLC shall provide aircraft appearance and janitorial services for all Boeing 787 aircraft operating at SEA.

Pricing Schedule:
- Boeing 787 RON (Remain Overnight) with lavatory and water service: $384.08 per event
- Turn cleaning with lavatory service: $125.50 per turn
- Deep clean service: $950.00 per event, scheduled quarterly

Service Level Agreement:
- RON cleaning must be completed within 4 hours of aircraft arrival
- Turn cleaning turnaround time: 35 minutes maximum
- On-time performance requirement: 98% monthly average

Penalties:
- Delay beyond SLA: $50 per 15-minute increment
- Monthly performance below 98%: $500 penalty per percentage point
- Repeat violations may result in contract termination per Article 12.3

Equipment Requirements:
- Ground Power Unit (GPU) must be available 24/7
- Potable water trucks must have 50-foot hoses for 787 operations
```

<Output>
entity{tuple_delimiter}G2 Secure Staff LLC{tuple_delimiter}vendor{tuple_delimiter}G2 Secure Staff LLC is the service provider for aircraft appearance and janitorial services at Seattle station.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is a widebody aircraft type requiring specialized ground handling and cleaning services.
entity{tuple_delimiter}Seattle Station{tuple_delimiter}location{tuple_delimiter}Seattle Station (SEA) is the airport location where ground services are provided.
entity{tuple_delimiter}RON Cleaning{tuple_delimiter}service{tuple_delimiter}RON (Remain Overnight) cleaning is a comprehensive aircraft cleaning service performed on aircraft staying overnight, including lavatory and water service.
entity{tuple_delimiter}Turn Cleaning{tuple_delimiter}service{tuple_delimiter}Turn cleaning is a quick turnaround cleaning service performed between flights with lavatory service.
entity{tuple_delimiter}Deep Clean{tuple_delimiter}service{tuple_delimiter}Deep clean is a comprehensive quarterly cleaning service for aircraft.
entity{tuple_delimiter}$384.08 RON Rate{tuple_delimiter}rate{tuple_delimiter}The rate for Boeing 787 RON cleaning with lavatory and water service is $384.08 per event.
entity{tuple_delimiter}$125.50 Turn Rate{tuple_delimiter}rate{tuple_delimiter}The rate for turn cleaning with lavatory service is $125.50 per turn.
entity{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}sla{tuple_delimiter}The service level agreement requires RON cleaning to be completed within 4 hours of aircraft arrival.
entity{tuple_delimiter}35-Minute Turn SLA{tuple_delimiter}sla{tuple_delimiter}Turn cleaning must be completed within 35 minutes maximum turnaround time.
entity{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}Service provider must maintain 98% monthly average on-time performance.
entity{tuple_delimiter}Delay Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond SLA incur a $50 penalty per 15-minute increment.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Monthly performance below 98% incurs a $500 penalty per percentage point below threshold.
entity{tuple_delimiter}Article 12.3{tuple_delimiter}contractterm{tuple_delimiter}Article 12.3 governs contract termination procedures for repeat violations.
entity{tuple_delimiter}Ground Power Unit{tuple_delimiter}equipment{tuple_delimiter}Ground Power Unit (GPU) is required equipment that must be available 24/7 for aircraft operations.
entity{tuple_delimiter}Potable Water Truck{tuple_delimiter}equipment{tuple_delimiter}Potable water trucks with 50-foot hoses are required for Boeing 787 water service operations.
relation{tuple_delimiter}G2 Secure Staff LLC{tuple_delimiter}Boeing 787{tuple_delimiter}service provision, ground handling{tuple_delimiter}G2 Secure Staff LLC provides aircraft appearance and janitorial services for Boeing 787 aircraft.
relation{tuple_delimiter}Boeing 787{tuple_delimiter}RON Cleaning{tuple_delimiter}aircraft service, cleaning requirement{tuple_delimiter}Boeing 787 aircraft receive RON cleaning service when remaining overnight.
relation{tuple_delimiter}RON Cleaning{tuple_delimiter}$384.08 RON Rate{tuple_delimiter}service pricing, cost structure{tuple_delimiter}RON cleaning service is priced at $384.08 per event.
relation{tuple_delimiter}RON Cleaning{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}service requirement, time constraint{tuple_delimiter}RON cleaning must comply with the 4-hour completion SLA.
relation{tuple_delimiter}Turn Cleaning{tuple_delimiter}35-Minute Turn SLA{tuple_delimiter}service requirement, turnaround time{tuple_delimiter}Turn cleaning is subject to a 35-minute maximum turnaround SLA.
relation{tuple_delimiter}4-Hour RON SLA{tuple_delimiter}Delay Penalty{tuple_delimiter}compliance enforcement, financial consequence{tuple_delimiter}Failure to meet the 4-hour RON SLA triggers the delay penalty structure.
relation{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}Performance Penalty{tuple_delimiter}performance measurement, penalty trigger{tuple_delimiter}Performance below 98% triggers the monthly performance penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}Article 12.3{tuple_delimiter}escalation path, contract enforcement{tuple_delimiter}Repeat violations resulting in performance penalties may lead to contract termination under Article 12.3.
relation{tuple_delimiter}Ground Power Unit{tuple_delimiter}Boeing 787{tuple_delimiter}equipment requirement, aircraft support{tuple_delimiter}GPU must be available 24/7 to support Boeing 787 operations.
relation{tuple_delimiter}Potable Water Truck{tuple_delimiter}Boeing 787{tuple_delimiter}specialized equipment, aircraft-specific requirement{tuple_delimiter}Potable water trucks with 50-foot hoses are specifically required for Boeing 787 water service.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Fuel Service Agreement – John F. Kennedy International Airport (JFK)

Service Provider: SkyFuel Services Inc. shall provide into-plane fueling for Boeing 787 operations at JFK. Fuel type: Jet A-1.

Pricing Schedule:
- Throughput fee: $0.015 per gallon
- Call-out fee (off-hours): $95.00 per call-out

Service Level Agreement (SLA):
- Fueling start within 25 minutes of block-on
- Max fueling completion time: 45 minutes
- On-time performance requirement: 97% monthly average

Penalties:
- Delay beyond SLA: $100 per 10-minute increment
- Performance below 97%: $400 penalty per percentage point

Contract Terms:
- Appendix B.4 details dispute resolution for fueling delays

Equipment Requirements:
- Hydrant dispenser with differential pressure gauge must be available
- Bonding cable must be attached before fueling commences
```

<Output>
entity{tuple_delimiter}SkyFuel Services Inc.{tuple_delimiter}vendor{tuple_delimiter}SkyFuel Services Inc. is the service provider responsible for into-plane fueling at JFK for Boeing 787 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is the aircraft type covered by the fueling service at JFK.
entity{tuple_delimiter}John F. Kennedy International Airport (JFK){tuple_delimiter}location{tuple_delimiter}JFK is the airport location where into-plane fueling services are provided.
entity{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}service{tuple_delimiter}Into-plane fueling involves delivering Jet A-1 fuel directly to the aircraft at the gate in accordance with the fueling agreement.
entity{tuple_delimiter}Jet A-1{tuple_delimiter}naturalobject{tuple_delimiter}Jet A-1 is the fuel type specified for Boeing 787 operations in the fueling agreement.
entity{tuple_delimiter}$0.015 Per Gallon Throughput Fee{tuple_delimiter}rate{tuple_delimiter}The throughput fee is $0.015 per gallon of fuel delivered.
entity{tuple_delimiter}$95.00 Call-Out Fee{tuple_delimiter}rate{tuple_delimiter}The call-out fee applies to off-hours fueling requests and is $95.00 per call-out.
entity{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}sla{tuple_delimiter}Fueling must start within 25 minutes of block-on time.
entity{tuple_delimiter}45-Minute Completion SLA{tuple_delimiter}sla{tuple_delimiter}Fueling must be completed within 45 minutes.
entity{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The service provider must maintain a 97% monthly average on-time performance.
entity{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond the SLA incur a $100 penalty per 10-minute increment.
entity{tuple_delimiter}Performance Below 97% Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 97% incurs a $400 penalty per percentage point below the threshold.
entity{tuple_delimiter}Appendix B.4{tuple_delimiter}contractterm{tuple_delimiter}Appendix B.4 describes dispute resolution procedures related to fueling delays.
entity{tuple_delimiter}Hydrant Dispenser{tuple_delimiter}equipment{tuple_delimiter}A hydrant dispenser equipped with a differential pressure gauge must be available for fueling operations.
entity{tuple_delimiter}Bonding Cable{tuple_delimiter}equipment{tuple_delimiter}A bonding cable must be attached prior to fueling to ensure safety.
relation{tuple_delimiter}SkyFuel Services Inc.{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}service provision{tuple_delimiter}SkyFuel Services Inc. provides into-plane fueling services.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Into-plane fueling is performed for Boeing 787 operations.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}Jet A-1{tuple_delimiter}fuel type{tuple_delimiter}Into-plane fueling uses Jet A-1 fuel.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}$0.015 Per Gallon Throughput Fee{tuple_delimiter}rate applicability{tuple_delimiter}The throughput fee applies to fuel delivered during into-plane fueling.
relation{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}$95.00 Call-Out Fee{tuple_delimiter}rate applicability{tuple_delimiter}Off-hours fueling requests are subject to the call-out fee.
relation{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}sla compliance{tuple_delimiter}Fueling must start within 25 minutes of block-on.
relation{tuple_delimiter}45-Minute Completion SLA{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}turnaround time{tuple_delimiter}Fueling must be completed within 45 minutes.
relation{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}25-Minute Start SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Delays beyond the start SLA trigger the delay penalty.
relation{tuple_delimiter}Performance Below 97% Penalty{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Monthly performance below 97% triggers the performance penalty.
relation{tuple_delimiter}Appendix B.4{tuple_delimiter}Delay Beyond SLA Penalty{tuple_delimiter}contract enforcement{tuple_delimiter}Appendix B.4 governs dispute resolution for fueling delays and related penalties.
relation{tuple_delimiter}Hydrant Dispenser{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}equipment requirement{tuple_delimiter}A hydrant dispenser is required for fueling operations.
relation{tuple_delimiter}Bonding Cable{tuple_delimiter}Into-Plane Fueling{tuple_delimiter}equipment requirement{tuple_delimiter}A bonding cable must be attached before fueling begins.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Catering Service Agreement – London Heathrow (LHR)

Service Provider: AeroCater Ltd shall provide catering uplift and waste removal for Boeing 787 and Airbus A350 operations at LHR.

Pricing Schedule:
- Meal uplift: $9.80 per passenger
- Special meal handling: $3.50 per special meal
- Waste removal: $85.00 per event
- Dry ice supply: $1.20 per kilogram
- Galley cart exchange: $12.00 per cart

Service Level Agreement (SLA):
- Uplift complete 40 minutes before STD
- Waste removal within 20 minutes of block-on
- Special meal confirmation 6 hours prior to STD
- On-time performance requirement: 98% monthly average

Penalties:
- Late uplift beyond SLA: $75 per 10-minute increment
- Missed special meal: $250 per flight
- Performance below 98%: $300 penalty per percentage point

Contract Terms:
- Schedule C Section 7 covers allergen handling procedures
- Annex D.2 governs waste segregation (recyclable vs general)

Equipment Requirements:
- Waste compactor must be available at the stand
- Galley carts must meet Atlas standard dimensions
- Dry ice gloves must be used when handling
```

<Output>
entity{tuple_delimiter}AeroCater Ltd{tuple_delimiter}vendor{tuple_delimiter}AeroCater Ltd is the service provider responsible for catering uplift and waste removal at LHR for Boeing 787 and Airbus A350 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is an aircraft type covered by the catering and waste services.
entity{tuple_delimiter}Airbus A350{tuple_delimiter}aircraft{tuple_delimiter}Airbus A350 is an aircraft type covered by the catering and waste services.
entity{tuple_delimiter}London Heathrow (LHR){tuple_delimiter}location{tuple_delimiter}LHR is the airport location where catering uplift and waste removal services are provided.
entity{tuple_delimiter}Catering Uplift{tuple_delimiter}service{tuple_delimiter}Catering uplift involves loading meals and beverages onto aircraft in accordance with service requirements.
entity{tuple_delimiter}Waste Removal{tuple_delimiter}service{tuple_delimiter}Waste removal involves the collection and disposal of aircraft cabin waste following flights.
entity{tuple_delimiter}Special Meal Handling{tuple_delimiter}service{tuple_delimiter}Special meal handling covers confirmation and provision of meals with specific dietary requirements.
entity{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}service{tuple_delimiter}Galley cart exchange involves replacing or swapping galley carts that meet Atlas standard dimensions.
entity{tuple_delimiter}Dry Ice{tuple_delimiter}naturalobject{tuple_delimiter}Dry ice is a consumable used for keeping catering items chilled and is supplied per kilogram.
entity{tuple_delimiter}$9.80 Meal Uplift Rate{tuple_delimiter}rate{tuple_delimiter}The rate for meal uplift is $9.80 per passenger.
entity{tuple_delimiter}$3.50 Special Meal Handling Rate{tuple_delimiter}rate{tuple_delimiter}The rate for special meal handling is $3.50 per special meal.
entity{tuple_delimiter}$85.00 Waste Removal Rate{tuple_delimiter}rate{tuple_delimiter}The rate for waste removal is $85.00 per event.
entity{tuple_delimiter}$1.20/kg Dry Ice Rate{tuple_delimiter}rate{tuple_delimiter}The rate for dry ice supply is $1.20 per kilogram.
entity{tuple_delimiter}$12.00 Galley Cart Exchange Rate{tuple_delimiter}rate{tuple_delimiter}The rate for galley cart exchange is $12.00 per cart.
entity{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}sla{tuple_delimiter}Catering uplift must be completed 40 minutes before scheduled time of departure (STD).
entity{tuple_delimiter}20-Minute Waste Removal SLA{tuple_delimiter}sla{tuple_delimiter}Waste removal must be completed within 20 minutes of block-on.
entity{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}sla{tuple_delimiter}Special meals must be confirmed 6 hours prior to scheduled time of departure.
entity{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The service provider must maintain a 98% monthly average on-time performance.
entity{tuple_delimiter}Late Uplift Penalty{tuple_delimiter}penalty{tuple_delimiter}Late catering uplift beyond SLA incurs a $75 penalty per 10-minute increment.
entity{tuple_delimiter}Missed Special Meal Penalty{tuple_delimiter}penalty{tuple_delimiter}A missed special meal incurs a $250 penalty per flight.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 98% incurs a $300 penalty per percentage point below the threshold.
entity{tuple_delimiter}Schedule C Section 7{tuple_delimiter}contractterm{tuple_delimiter}Schedule C Section 7 covers allergen handling procedures for catering services.
entity{tuple_delimiter}Annex D.2{tuple_delimiter}contractterm{tuple_delimiter}Annex D.2 governs waste segregation requirements (recyclable vs general).
entity{tuple_delimiter}Waste Compactor{tuple_delimiter}equipment{tuple_delimiter}A waste compactor must be available at the stand for cabin waste processing.
entity{tuple_delimiter}Atlas Standard Galley Cart{tuple_delimiter}equipment{tuple_delimiter}Galley carts must meet Atlas standard dimensions.
entity{tuple_delimiter}Dry Ice Gloves{tuple_delimiter}equipment{tuple_delimiter}Dry ice gloves must be used when handling dry ice for safety.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Catering Uplift{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd provides catering uplift services.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Waste Removal{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd provides waste removal services.
relation{tuple_delimiter}AeroCater Ltd{tuple_delimiter}Special Meal Handling{tuple_delimiter}service provision{tuple_delimiter}AeroCater Ltd manages special meal handling and confirmations.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Catering uplift is performed for Boeing 787 operations at LHR.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}Airbus A350{tuple_delimiter}aircraft type coverage{tuple_delimiter}Catering uplift is performed for Airbus A350 operations at LHR.
relation{tuple_delimiter}Catering Uplift{tuple_delimiter}$9.80 Meal Uplift Rate{tuple_delimiter}rate applicability{tuple_delimiter}Meal uplift is billed at $9.80 per passenger.
relation{tuple_delimiter}Special Meal Handling{tuple_delimiter}$3.50 Special Meal Handling Rate{tuple_delimiter}rate applicability{tuple_delimiter}Special meal handling is billed at $3.50 per special meal.
relation{tuple_delimiter}Waste Removal{tuple_delimiter}$85.00 Waste Removal Rate{tuple_delimiter}rate applicability{tuple_delimiter}Waste removal is billed at $85.00 per event.
relation{tuple_delimiter}Dry Ice{tuple_delimiter}$1.20/kg Dry Ice Rate{tuple_delimiter}rate applicability{tuple_delimiter}Dry ice supply is billed at $1.20 per kilogram.
relation{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}$12.00 Galley Cart Exchange Rate{tuple_delimiter}rate applicability{tuple_delimiter}Galley cart exchange is billed at $12.00 per cart.
relation{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}Catering Uplift{tuple_delimiter}sla compliance{tuple_delimiter}Catering uplift must be complete 40 minutes before STD.
relation{tuple_delimiter}20-Minute Waste Removal SLA{tuple_delimiter}Waste Removal{tuple_delimiter}turnaround time{tuple_delimiter}Waste removal must be completed within 20 minutes of block-on.
relation{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}Special Meal Handling{tuple_delimiter}sla compliance{tuple_delimiter}Special meals must be confirmed 6 hours prior to STD.
relation{tuple_delimiter}Late Uplift Penalty{tuple_delimiter}40-Minute Pre-STD Uplift SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Late uplift beyond the SLA triggers the late uplift penalty.
relation{tuple_delimiter}Missed Special Meal Penalty{tuple_delimiter}6-Hour Special Meal Confirmation SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Failure to confirm special meals on time triggers the missed special meal penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}98% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Performance below 98% triggers the monthly performance penalty.
relation{tuple_delimiter}Schedule C Section 7{tuple_delimiter}Special Meal Handling{tuple_delimiter}contract enforcement{tuple_delimiter}Allergen handling procedures apply to special meal handling.
relation{tuple_delimiter}Annex D.2{tuple_delimiter}Waste Removal{tuple_delimiter}contract enforcement{tuple_delimiter}Waste segregation requirements apply to waste removal services.
relation{tuple_delimiter}Waste Compactor{tuple_delimiter}Waste Removal{tuple_delimiter}equipment requirement{tuple_delimiter}A waste compactor must be available for cabin waste processing.
relation{tuple_delimiter}Atlas Standard Galley Cart{tuple_delimiter}Galley Cart Exchange{tuple_delimiter}equipment requirement{tuple_delimiter}Galley carts must meet Atlas standard dimensions.
relation{tuple_delimiter}Dry Ice Gloves{tuple_delimiter}Catering Uplift{tuple_delimiter}equipment requirement{tuple_delimiter}Dry ice gloves must be used when handling dry ice during catering uplift.
{completion_delimiter}

""",
    """<Entity_types>
["Person","Organization","Location","Event","Service","Aircraft","Rate","Vendor","SLA","Penalty","ContractTerm","Equipment","NaturalObject","Concept"]

<Input Text>
```
Deicing Service Agreement – Denver International Airport (DEN)

Service Provider: FrostJet Services shall provide Type I deicing and Type IV anti-icing for Boeing 787 operations at DEN.

Pricing Schedule:
- Type I fluid application: $2.75 per gallon
- Type IV fluid application: $4.20 per gallon
- Call-out fee (off-hours): $180.00 per call-out
- Pad occupancy: $35.00 per 10-minute increment

Service Level Agreement (SLA):
- Deicing start within 15 minutes of request
- Max deicing completion time: 30 minutes
- Holdover time calculation per SAE tables
- On-time performance requirement: 97% monthly average

Penalties:
- Delay beyond SLA: $120 per 10-minute increment
- Incorrect holdover time computation: $500 per event
- Performance below 97%: $400 penalty per percentage point

Contract Terms:
- Exhibit E defines fluid dilution ratios and environmental discharge limits

Equipment Requirements:
- Heated spray rigs with viscosity monitors must be used
- Glycol recovery systems are required on the pad
- Safety cones and marshallers must be present during operations
```

<Output>
entity{tuple_delimiter}FrostJet Services{tuple_delimiter}vendor{tuple_delimiter}FrostJet Services is the provider of deicing and anti-icing services at DEN for Boeing 787 operations.
entity{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft{tuple_delimiter}Boeing 787 is the aircraft type covered by the deicing agreement.
entity{tuple_delimiter}Denver International Airport (DEN){tuple_delimiter}location{tuple_delimiter}DEN is the airport location where deicing services are provided.
entity{tuple_delimiter}Type I Deicing{tuple_delimiter}service{tuple_delimiter}Type I deicing involves applying heated fluid to remove frost, ice, and snow from aircraft surfaces.
entity{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}service{tuple_delimiter}Type IV anti-icing involves applying fluid to delay ice accretion after deicing.
entity{tuple_delimiter}Type I Fluid{tuple_delimiter}naturalobject{tuple_delimiter}Type I deicing fluid is used to remove contamination and is billed per gallon.
entity{tuple_delimiter}Type IV Fluid{tuple_delimiter}naturalobject{tuple_delimiter}Type IV anti-icing fluid is used to prevent re-accumulation and is billed per gallon.
entity{tuple_delimiter}$2.75 Type I Rate{tuple_delimiter}rate{tuple_delimiter}The application rate for Type I fluid is $2.75 per gallon.
entity{tuple_delimiter}$4.20 Type IV Rate{tuple_delimiter}rate{tuple_delimiter}The application rate for Type IV fluid is $4.20 per gallon.
entity{tuple_delimiter}$180.00 Call-Out Fee{tuple_delimiter}rate{tuple_delimiter}The off-hours call-out fee is $180.00 per call-out.
entity{tuple_delimiter}$35.00 Pad Occupancy Fee{tuple_delimiter}rate{tuple_delimiter}Pad occupancy is billed at $35.00 per 10-minute increment.
entity{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}sla{tuple_delimiter}Deicing must start within 15 minutes of the service request.
entity{tuple_delimiter}30-Minute Completion SLA{tuple_delimiter}sla{tuple_delimiter}Deicing must be completed within 30 minutes.
entity{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}sla{tuple_delimiter}Holdover time must be calculated according to SAE tables.
entity{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}sla{tuple_delimiter}The provider must maintain a 97% monthly average on-time performance.
entity{tuple_delimiter}Delay Penalty{tuple_delimiter}penalty{tuple_delimiter}Delays beyond the SLA incur a $120 penalty per 10-minute increment.
entity{tuple_delimiter}Holdover Computation Penalty{tuple_delimiter}penalty{tuple_delimiter}Incorrect holdover time computation incurs a $500 penalty per event.
entity{tuple_delimiter}Performance Penalty{tuple_delimiter}penalty{tuple_delimiter}Performance below 97% incurs a $400 penalty per percentage point below the threshold.
entity{tuple_delimiter}Exhibit E{tuple_delimiter}contractterm{tuple_delimiter}Exhibit E defines fluid dilution ratios and environmental discharge limits for deicing operations.
entity{tuple_delimiter}Heated Spray Rig{tuple_delimiter}equipment{tuple_delimiter}A heated spray rig equipped with viscosity monitors must be used during deicing.
entity{tuple_delimiter}Glycol Recovery System{tuple_delimiter}equipment{tuple_delimiter}A glycol recovery system is required on the pad to collect runoff.
entity{tuple_delimiter}Safety Cones{tuple_delimiter}equipment{tuple_delimiter}Safety cones and marshallers must be present during deicing operations for safety.
relation{tuple_delimiter}FrostJet Services{tuple_delimiter}Type I Deicing{tuple_delimiter}service provision{tuple_delimiter}FrostJet Services provides Type I deicing.
relation{tuple_delimiter}FrostJet Services{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}service provision{tuple_delimiter}FrostJet Services provides Type IV anti-icing.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Type I deicing is performed for Boeing 787 operations.
relation{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}Boeing 787{tuple_delimiter}aircraft type coverage{tuple_delimiter}Type IV anti-icing is performed for Boeing 787 operations.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}$2.75 Type I Rate{tuple_delimiter}rate applicability{tuple_delimiter}Type I fluid application is billed at $2.75 per gallon.
relation{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}$4.20 Type IV Rate{tuple_delimiter}rate applicability{tuple_delimiter}Type IV fluid application is billed at $4.20 per gallon.
relation{tuple_delimiter}Type I Deicing{tuple_delimiter}$180.00 Call-Out Fee{tuple_delimiter}rate applicability{tuple_delimiter}Off-hours deicing requests are subject to the call-out fee.
relation{tuple_delimiter}Pad Occupancy{tuple_delimiter}$35.00 Pad Occupancy Fee{tuple_delimiter}rate applicability{tuple_delimiter}Pad occupancy during deicing is billed per 10-minute increment.
relation{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}Type I Deicing{tuple_delimiter}sla compliance{tuple_delimiter}Deicing must start within 15 minutes of request.
relation{tuple_delimiter}30-Minute Completion SLA{tuple_delimiter}Type I Deicing{tuple_delimiter}turnaround time{tuple_delimiter}Deicing must be completed within 30 minutes.
relation{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}Type IV Anti-Icing{tuple_delimiter}sla compliance{tuple_delimiter}Holdover time must be calculated according to SAE tables when applying Type IV.
relation{tuple_delimiter}Delay Penalty{tuple_delimiter}15-Minute Start SLA{tuple_delimiter}penalty trigger{tuple_delimiter}Delay beyond the start SLA triggers the delay penalty.
relation{tuple_delimiter}Holdover Computation Penalty{tuple_delimiter}Holdover Time Compliance{tuple_delimiter}penalty trigger{tuple_delimiter}Incorrect holdover calculations trigger the penalty.
relation{tuple_delimiter}Performance Penalty{tuple_delimiter}97% On-Time Requirement{tuple_delimiter}penalty trigger{tuple_delimiter}Monthly performance below 97% triggers the performance penalty.
relation{tuple_delimiter}Exhibit E{tuple_delimiter}Type I Deicing{tuple_delimiter}contract enforcement{tuple_delimiter}Fluid dilution ratios and environmental limits govern deicing operations.
relation{tuple_delimiter}Heated Spray Rig{tuple_delimiter}Type I Deicing{tuple_delimiter}equipment requirement{tuple_delimiter}Heated spray rigs with viscosity monitors must be used during deicing.
relation{tuple_delimiter}Glycol Recovery System{tuple_delimiter}Type I Deicing{tuple_delimiter}equipment requirement{tuple_delimiter}Glycol recovery systems must be used to collect runoff.
relation{tuple_delimiter}Safety Cones{tuple_delimiter}Type I Deicing{tuple_delimiter}safety requirement{tuple_delimiter}Safety cones and marshallers must be present during operations.
{completion_delimiter}

""",
]

PROMPTS["summarize_entity_descriptions"] = """## Role
You are a Knowledge Graph Specialist proficient in data curation and synthesis.

## Task
Synthesize a list of descriptions about an entity or relation into a single, cohesive summary.

## Instructions
- Input: JSON objects, one per line in the Description List.
- Output: plain text summary with short paragraphs; no extra comments.
- Integrate all key information from every description.
- Write objectively in third person; begin with the full name of the entity/relation.
- Handle conflicts: separate distinct entities/relations; note unresolved discrepancies.
- Keep within {summary_length} tokens while maintaining completeness.
- Language: {language}. Retain proper nouns; preserve numbers, percentages, currency symbols, and units exactly.
- Grounding: Use only the provided descriptions; do not add external knowledge.
- Do not mention context, implementation details, or prompts in the output.

## Input
{description_type} Name: {description_name}

Description List:

```
{description_list}
```

## Output
"""

PROMPTS["fail_response"] = (
    "Sorry, I'm not able to provide an answer to that question.[no-context]"
)

PROMPTS["rag_response"] = """## Role

You are a Senior Airline Procurement Specialist with expertise in ground handling agreements, catering contracts, fuel service agreements, and SGHA. Answer user queries using only the provided materials while protecting airline operational interests.

**CRITICAL REQUIREMENT: You MUST add [n] citation numbers immediately after EVERY fact you state. This is non-negotiable.**

## Goal

Produce a concise, well-structured answer that integrates relevant facts from Knowledge Graph and Document Chunks. **Every single fact must have an inline citation [n] immediately following it.**

## MANDATORY CITATION RULES (READ CAREFULLY)

**BEFORE YOU WRITE ANYTHING, UNDERSTAND THIS:**
- EVERY sentence containing a fact MUST end with [n] before the period
- EVERY bullet point MUST have [n] after the fact
- NO EXCEPTIONS - even obvious facts need citations
- If you forget citations, your answer is INVALID

**WRONG (Missing citations):**
```
TCI measures on-time reliability for cabin cleaning.
Performance is based on Cabin Cleaning Off Time.
```

**CORRECT (With required citations):**
```
TCI measures on-time reliability for cabin cleaning [1].
Performance is based on Cabin Cleaning Off Time [2].
```

## Instructions

**YOU MUST USE INLINE CITATIONS FOR EVERY FACT - THIS IS MANDATORY**

1. Determine the user intent from the conversation.
2. Extract only directly relevant facts from the supplied materials.
3. Compose a cohesive answer without external assumptions.
4. **MANDATORY**: Place [n] citation markers immediately after EVERY SINGLE fact, claim, or statement.
   - WRONG: "TCI measures on-time reliability of cabin cleaning activities"
   - CORRECT: "TCI measures on-time reliability of cabin cleaning activities [1]"
   - WRONG: "Performance is assessed based on cabin off time"
   - CORRECT: "Performance is assessed based on cabin off time [2]"
5. Do NOT group all citations at the end - citations must appear inline with each fact.
6. Generate a References section at the end listing ONLY the sources you actually cited in the answer body; no extras.
7. Use ONLY the [n] IDs from the Reference Document List in the Materials; reuse the same [n] for repeat citations of the same source; do NOT invent or renumber IDs.
8. Ensure bidirectional consistency: every [n] in the answer appears in References, and every entry in References is cited at least once in the answer.
9. Order References by first appearance of their [n] in the answer.
10. Do not include any text after the References section.
11. Do not mention context, implementation details, or prompts in the output.

## Content & Grounding

- Use only the provided materials; never invent or infer.
- If insufficient information exists, state that more information is required.
- Preserve currency symbols, percentages, and units exactly; do not compute totals unless provided.
- Prefer entries with most recent effective dates when asked for “latest/current.”
- Clarify scope (e.g., RON vs Turn, aircraft types, station-specific rates) strictly from provided materials.

## Formatting & Language

- Respond in the user’s language.
- Use GitHub Flavored Markdown (headings, bold text, bullet points).
- Present the response in {response_type}.
- Do NOT mention or expose document version markers, sequence indices, or tokens like [vN] in your answer.

## Inline Citation Format

- Place [n] immediately after each fact: "The price is $500 [1]."
- Multiple facts: "The RON service costs $500 [1] and includes lavatory service [2]."
- Every bullet point should have at least one citation.
- Citations go INSIDE the sentence, not at the end of paragraphs.

## References Section Format

- Heading: `### References`
- Each entry: `- [n] Document Title` (IDs must match the Reference Document List; include ONLY cited sources)
- Titles must keep original language.
- One citation per line; no text after references.

## Reference Section Example
```
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
```

## Additional Instructions
{user_prompt}

## Materials
{context_data}
"""

PROMPTS["naive_rag_response"] = """## Role

You are a Senior Airline Procurement Specialist. Answer user queries using only the provided document chunks, focusing on protecting airline operational interests.

**CRITICAL REQUIREMENT: You MUST add [n] citation numbers immediately after EVERY fact you state. This is non-negotiable.**

## Goal

Produce a concise, well-structured answer that integrates relevant facts from Document Chunks. **Every single fact must have an inline citation [n] immediately following it.**

## MANDATORY CITATION RULES (READ CAREFULLY)

**BEFORE YOU WRITE ANYTHING, UNDERSTAND THIS:**
- EVERY sentence containing a fact MUST end with [n] before the period
- EVERY bullet point MUST have [n] after the fact
- NO EXCEPTIONS - even obvious facts need citations
- If you forget citations, your answer is INVALID

**WRONG (Missing citations):**
```
TCI measures on-time reliability for cabin cleaning.
Performance is based on Cabin Cleaning Off Time.
```

**CORRECT (With required citations):**
```
TCI measures on-time reliability for cabin cleaning [1].
Performance is based on Cabin Cleaning Off Time [2].
```

## Instructions

**YOU MUST USE INLINE CITATIONS FOR EVERY FACT - THIS IS MANDATORY**

1. Determine the user intent from the conversation.
2. Extract only directly relevant facts from the provided chunks.
3. Compose a cohesive answer without external assumptions.
4. **MANDATORY**: Place [n] citation markers immediately after EVERY SINGLE fact, claim, or statement.
   - WRONG: "TCI measures on-time reliability of cabin cleaning activities"
   - CORRECT: "TCI measures on-time reliability of cabin cleaning activities [1]"
   - WRONG: "Performance is assessed based on cabin off time"
   - CORRECT: "Performance is assessed based on cabin off time [2]"
5. Do NOT group all citations at the end - citations must appear inline with each fact.
6. Generate a References section at the end listing ONLY the sources you actually cited in the answer body; no extras.
7. Use ONLY the [n] IDs from the Reference Document List in the Materials; reuse the same [n] for repeat citations of the same source; do NOT invent or renumber IDs.
8. Ensure bidirectional consistency: every [n] in the answer appears in References, and every entry in References is cited at least once in the answer.
9. Order References by first appearance of their [n] in the answer.
10. Do not include any text after the References section.
11. Do not mention context, implementation details, or prompts in the output.

## Content & Grounding

- Use only the provided chunks; never invent or infer.
- If insufficient information exists, state that more information is required.

## Formatting & Language

- Respond in the user’s language.
- Use GitHub Flavored Markdown (headings, bold text, bullet points).
- Present the response in {response_type}.
- Do NOT mention or expose document version markers, sequence indices, or tokens like [vN] in your answer.

## Inline Citation Format

- Place [n] immediately after each fact: "The price is $500 [1]."
- Multiple facts: "The RON service costs $500 [1] and includes lavatory service [2]."
- Every bullet point should have at least one citation.
- Citations go INSIDE the sentence, not at the end of paragraphs.

## References Section Format

- Heading: `### References`
- Each entry: `- [n] Document Title` (IDs must match the Reference Document List; include ONLY cited sources)
- Titles must keep original language.
- One citation per line; no text after references.

## Reference Section Example
```
### References

- [1] Document Title One
- [2] Document Title Two
- [3] Document Title Three
```

## Additional Instructions
{user_prompt}

## Materials
{content_data}
"""

PROMPTS["kg_query_context"] = """
---Document Versioning Information---
This knowledge graph contains versioned data marked with [v1], [v2], [v3], [v4], etc.
- Higher version numbers indicate MORE RECENT information (e.g., [v4] is newer than [v1])
- Entities, relationships, and document chunks may all contain version markers
- When answering queries about "latest" or "current" information, prioritize data with HIGHER version numbers
- Version markers appear at the end of entity names, relationship references, and document chunk content
- In document chunks, the "sequence_index" field corresponds to the version number (sequence_index: 4 = [v4], sequence_index: 1 = [v1])

Knowledge Graph Data (Entity):

```json
{entities_str}
```

Knowledge Graph Data (Relationship):

```json
{relations_str}
```

Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{text_chunks_str}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
{reference_list_str}
```

"""

PROMPTS["naive_query_context"] = """
Document Chunks (Each entry has a reference_id refer to the `Reference Document List`):

```json
{text_chunks_str}
```

Reference Document List (Each entry starts with a [reference_id] that corresponds to entries in the Document Chunks):

```
{reference_list_str}
```

"""

PROMPTS["keywords_extraction"] = """---Role---
You are an expert keyword extractor, specializing in analyzing user queries for a Retrieval-Augmented Generation (RAG) system. Your purpose is to identify both high-level and low-level keywords in the user's query that will be used for effective document retrieval.

---Goal---
Given a user query, your task is to extract two distinct types of keywords:
1. **high_level_keywords**: for overarching concepts or themes, capturing user's core intent, the subject area, or the type of question being asked.
2. **low_level_keywords**: for specific entities or details, identifying the specific entities, proper nouns, technical jargon, product names, or concrete items.

---Instructions & Constraints---
1. **Output Format**: Your output MUST be a valid JSON object and nothing else. Do not include any explanatory text, markdown code fences (like ```json), or any other text before or after the JSON. It will be parsed directly by a JSON parser.
2. **Source of Truth**: All keywords must be explicitly derived from the user query, with both high-level and low-level keyword categories are required to contain content.
3. **Concise & Meaningful**: Keywords should be concise words or meaningful phrases. Prioritize multi-word phrases when they represent a single concept. For example, from "latest financial report of Apple Inc.", you should extract "latest financial report" and "Apple Inc." rather than "latest", "financial", "report", and "Apple".
4. **Handle Edge Cases**: For queries that are too simple, vague, or nonsensical (e.g., "hello", "ok", "asdfghjkl"), you must return a JSON object with empty lists for both keyword types.
5. **Language**: All extracted keywords MUST be in {language}. Proper nouns (e.g., personal names, place names, organization names) should be kept in their original language.

---Examples---
{examples}

---Real Data---
User Query: {query}

---Output---
Output:"""

PROMPTS["keywords_extraction_examples"] = [
    """Example 1:

Query: "What are the Boeing 787 RON cleaning rates at Seattle station?"

Output:
{
  "high_level_keywords": ["Aircraft cleaning rates", "Ground handling pricing", "Service costs"],
  "low_level_keywords": ["Boeing 787", "RON", "Seattle", "SEA", "Cleaning service", "Pricing"]
}

""",
    """Example 2:

Query: "What are the SLA requirements for pushback services?"

Output:
{
  "high_level_keywords": ["Service level agreement", "Performance requirements", "Ground handling standards"],
  "low_level_keywords": ["Pushback", "SLA", "Turnaround time", "On-time performance", "KPI"]
}

""",
    """Example 3:

Query: "Can we terminate the contract for vendor performance issues?"

Output:
{
  "high_level_keywords": ["Contract termination", "Vendor management", "Performance clauses"],
  "low_level_keywords": ["Termination rights", "Performance violations", "Notice period", "Penalties"]
}

""",
    """Example 4:

Query: "How does international trade influence global economic stability?"

Output:
{
  "high_level_keywords": ["International trade", "Global economic stability", "Economic impact"],
  "low_level_keywords": ["Trade agreements", "Tariffs", "Currency exchange", "Imports", "Exports"]
}

""",
]

# Temporal RAG Response Prompt (Sprint 7: Airline Domain Specialization)
PROMPTS["temporal_response"] = """## Role

You are a Senior Airline Procurement Specialist analyzing SGHA, Catering Contracts, and Fuel Service Agreements. Provide accurate, actionable answers to protect airline interests.

**CRITICAL REQUIREMENT: You MUST add [n] citation numbers immediately after EVERY fact you state. This is non-negotiable.**

## Critical

Analyze the Latest Signed Text (highest sequence number) as the current legally binding version, regardless of effective dates inside the document.

## Goal

- Quantitative queries: crisp tabular data **with inline citations [n]**
- Qualitative queries: structured analysis **with inline citations [n]**

## MANDATORY CITATION RULES (READ CAREFULLY)

**BEFORE YOU WRITE ANYTHING, UNDERSTAND THIS:**
- EVERY sentence containing a fact MUST end with [n] before the period
- EVERY bullet point MUST have [n] after the fact
- EVERY table cell with data MUST have [n] after the value
- NO EXCEPTIONS - even obvious facts need citations
- If you forget citations, your answer is INVALID

**WRONG (Missing citations):**
```
TCI measures on-time reliability for cabin cleaning.
The RON service costs $384.08.
```

**CORRECT (With required citations):**
```
TCI measures on-time reliability for cabin cleaning [1].
The RON service costs $384.08 [2].
```

## Temporal Awareness

- Recognize `<EFFECTIVE_DATE confidence="X">YYYY-MM-DD</EFFECTIVE_DATE>` tags
- Future effective date indicates scheduled activation
- Past effective date indicates current activation
- No tag implies active upon signing
- Distinguish sections with differing effective dates

## Vocabulary

- SGHA, Annex/Exhibit B, MCT, GPU/ASU, RON, Turn, Red Eye, Deep Clean, Lav Service, Potable Water, SLA, KPI

## Instructions

1. Query Classification
  - Mode A (Quantitative): rates, fees, dates, dimensions
  - Mode B (Qualitative): clauses, liability, termination, obligations

2. Confidence Tag Interpretation
  - Future date: indicate not yet active and include the date
  - Past date: treat as active
  - No date: treat as active
  - Multiple dates: clearly separate entries

3. Mode A: Quantitative Format
  - Use a Markdown table; no intro text
  - Columns: Service Item | Rate (Currency) | Unit | Effective Date
  - **MANDATORY**: Add [n] citation after EVERY rate value in the table
  - Add "(Scheduled)" or "(Not Yet Active)" in Rate column when applicable
  - Example table cell: "$384.08 [1]" or "$500.00 (Scheduled) [2]"

4. Mode B: Qualitative Format
  - Brief Answer: 2–3 natural sentences from the airline procurement perspective **with [n] citations after every fact**; mention future effective dates if applicable.
  - Key Points: 3–5 concise bullets covering obligations, rights, effective dates, and operational impact **with [n] citations after every bullet point**.
  - Constraints: short list for conditions, exceptions, time limits, and penalties **with [n] citations**.
  - Keep the tone straightforward and plain; avoid legalese and unnecessary verbosity.
  - **CRITICAL**: Every bullet point, every sentence must have inline [n] citations.

## Inline Citation Format (MANDATORY)

- Place [n] immediately after each fact: "The price is $500 [1]."
- In tables: "RON Service | $384.08 [1] | per event | 2024-01-01"
- Multiple facts: "The RON service costs $500 [1] and includes lavatory service [2]."
- Every bullet point must have at least one citation.
- Citations go INSIDE the sentence, not at the end of paragraphs.

## Citation & References

- Do not mention version numbers, sequence indices, or tokens like [vN]
- Do not include internal implementation details
- Extract filenames from the Reference Document List
- **Every fact in your answer must have a corresponding [n] inline citation**

### Bidirectional Citation Consistency (MANDATORY)
- Use ONLY [n] IDs from the Reference Document List; reuse the same [n] when citing the same source again.
- References must include EXACTLY the sources cited in the answer (no extras), ordered by first appearance of their [n].
- Every [n] used in the answer MUST have a corresponding entry in References; every entry in References MUST be cited at least once in the answer.

### References Section Format
```
**[N]. Document Name**
  - File: [filename from Reference Document List]
  - Section: [main section name]
  - Subsection: [optional]
  - Details: [brief detail or page reference]
```

### Good References Example
```markdown
### References

**1. EXHIBIT B – SEA Cabin Cleaning**
  - File: SEA_G2_Cabin_Cleaning_Exhibit_B_2025.pdf
  - Section: Boeing 787 Services
  - Subsection: RON (Remain Overnight) Services
  - Details: Row "Ron w/lav & water", Rate: $384.08

**2. Service Agreement Amendment**
  - File: Service_Agreement_Amendment_2024.pdf
  - Section: Pricing Schedule
  - Details: Effective Date: 2024-06-01

**3. Master Service Agreement**
  - File: Master_Service_Agreement.pdf
  - Section: 4.1 Payment Terms
  - Subsection: 4.1.2 Invoicing Requirements
```

## Content & Grounding

- Base answers only on provided materials
- If information is missing, state that it is not available
- Preserve `<EFFECTIVE_DATE>` tags when present

## Language & Formatting

- Respond in the user’s language
- Use GitHub Flavored Markdown
 - Mode A: table mandatory; no source column and no SLA/KPI column
- Mode B: headings, bold, bullets
- Present the response in {response_type}
- Keep References concise and non-redundant
- Do not mention context, implementation details, or prompts in the output

## Additional Instructions
{user_prompt}

## Materials
{context_data}
"""
