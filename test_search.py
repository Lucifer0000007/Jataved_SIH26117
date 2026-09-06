import search

r = search.search("What is the pre-start checklist for pump P-101A?", "Shift Engineer (E-1042)")
for doc, meta, dist in r[:2]:
    print(round(dist, 3), meta["file"], "|", doc[:80].replace("\n", " "))

print(search.search("leak response procedure", "Junior Trainee (T-201)"))