import pgeocode

nomi = pgeocode.Nominatim('us')
response_pgeo = nomi.query_location("Santa Cruz", top_k=3)
print(response_pgeo)