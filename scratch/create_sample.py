import pandas as pd

data = {
    'Nama': ['Budi Santoso', 'Siti Aminah', 'Agus Prayogo', 'Dewi Lestari', 'Eko Saputra']
}

df = pd.DataFrame(data)
df.to_excel('sample_panitia.xlsx', index=False)
print("Sample Excel created.")
