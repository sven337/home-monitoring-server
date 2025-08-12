import pandas as pd
import glob
import os
from pysolar import solar
import pandas as pd
from configparser import ConfigParser
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt
import pickle

# Read the configuration file
config = ConfigParser()
config.read('../pvmonitor.cfg')

LATITUDE = config.getfloat('LOCATION', 'latitude')
LONGITUDE = config.getfloat('LOCATION', 'longitude')


# Path to the directory containing your CSV files
path = '.'


# May or may not be needed - useful for long term historic ratios since they're not exactly 25% (silicon lottery?)
historic_yields = { "hm1500_total" : 2073.698, "hm1500_ch1" : 506.595, "hm1500_ch2" : 514.938, "hm1500_ch3" :  542.584, "hm1500_ch4": 509.581,
                   "hm1500_2_total" : 1022.896, "hm1500_2_ch1": 338.036, "hm1500_2_ch2" : 	344.111, "hm1500_2_ch3": 339.880, "hm1500_2_ch4":	 0.869 }

def calculate_ratios(df):
    for c in df.columns:
        if not "hm1500" in c:
            continue

        if "powerdc" in c:
            continue

        powerdc_column = ""
        if 'hm1500_2' in c:
            powerdc_column = 'hm1500_2_powerdc'
        else:
            powerdc_column = 'hm1500_powerdc'

        newcol = c
        newcol = newcol.replace("hm1500_2_ch", "2p")
        newcol = newcol.replace("hm1500_ch", "1p")
        newcol = newcol.replace("power", "ratio")
        print(f"Calculating ratios {newcol} from {c}") 

        df[newcol] = df[c] / df[powerdc_column] 
#        df = df.drop(c, axis=1)
    return df


def add_sun_positions(df):
    def get_sun_position(date):
        date_utc = date.tz_convert('UTC')
        altitude = solar.get_altitude(LATITUDE, LONGITUDE, date_utc)
        azimuth = solar.get_azimuth(LATITUDE, LONGITUDE, date_utc)
        return pd.Series({'sun_elevation': altitude, 'sun_azimuth': azimuth})

    df[['sun_elevation', 'sun_azimuth']] = df.index.to_series().apply(get_sun_position)

    print(df.head())

def sun_position_heatmap(df, doSavePic = False, doSaveFile = False):
    ratio_columns = [col for col in df.columns if col.endswith('_ratio')]
    n_buckets = 12  

    # Create histogram-based buckets and get ranges
    elevation_bins = pd.qcut(df['sun_elevation'], q=n_buckets)
    azimuth_bins = pd.qcut(df['sun_azimuth'], q=n_buckets)

    # Create labels with ranges
    elevation_labels = [f'E{i+1}: {r.left:.1f}°-{r.right:.1f}°' for i, r in enumerate(elevation_bins.cat.categories)]
    azimuth_labels = [f'A{i+1}: {r.left:.1f}°-{r.right:.1f}°' for i, r in enumerate(azimuth_bins.cat.categories)]

    # Assign labels to dataframe
    df['elevation_bucket'] = pd.qcut(df['sun_elevation'], q=n_buckets, labels=elevation_labels)
    df['azimuth_bucket'] = pd.qcut(df['sun_azimuth'], q=n_buckets, labels=azimuth_labels)

# Function to calculate mean ratios for each column
    def mean_ratios(group):
        return group[ratio_columns].mean()

# Group by elevation and azimuth buckets and calculate mean ratios
    elevation_ratios = df.groupby('elevation_bucket').apply(mean_ratios)
    azimuth_ratios = df.groupby('azimuth_bucket').apply(mean_ratios)
    print("Mean ratios by elevation bucket:")
    print(elevation_ratios)
    print("\nMean ratios by azimuth bucket:")
    print(azimuth_ratios)


    # Dictionary to store pivot tables and standard deviations
    pivot_tables = {}
    std_dev_tables = {}

# Create a heatmap for a specific ratio (e.g., '1p1_ratio')
    for c in ratio_columns:
        pivot_table = df.pivot_table(values=c, index='elevation_bucket', columns='azimuth_bucket', aggfunc='mean')
        std_dev_table = df.pivot_table(values=c, index='elevation_bucket', columns='azimuth_bucket', aggfunc='std')

        pivot_tables[c] = pivot_table
        std_dev_tables[c] = std_dev_table
       
        # Create annotation array
        annot = np.empty_like(pivot_table, dtype=object)
        for i in range(pivot_table.shape[0]):
            for j in range(pivot_table.shape[1]):
                mean_value = pivot_table.iloc[i, j]
                std_value = std_dev_table.iloc[i, j]
                annot[i, j] = f'{mean_value:.2f}\n±{std_value:.2f}'

        fig, ax = plt.subplots(figsize=(15, 10))
        sns.heatmap(pivot_table, annot=annot, fmt='', center=pivot_table.mean().mean(), ax=ax)
    
        ax.invert_yaxis()  # Invert the Y-axis
        ax.set_title(f'{c} by Sun Position (Histogram Buckets)')
        ax.set_ylabel('Elevation')
        ax.set_xlabel('Azimuth')

        # Rotate x-axis labels for better readability
        plt.xticks(rotation=45, ha='right')
        plt.yticks(rotation=0)

        plt.teht_layout()
        if doSavePic:
            plt.savefig(f'./{c}.png')

    # Save data to file
    if doSaveFile:
        data_to_save = {
            'pivot_tables': pivot_tables,
            'std_dev_tables': std_dev_tables,
            'elevation_bins': elevation_bins,
            'azimuth_bins': azimuth_bins
        }
        with open('panel_historical_ratios_from_sun_position.pkl', 'wb') as f:
            pickle.dump(data_to_save, f)
            f.flush()
            f.close()

    return pivot_tables, std_dev_tables, elevation_bins, azimuth_bins



def year_progress(timestamp):
    # Ensure we're working with timezone-aware timestamps
    if timestamp.tzinfo is None:
        raise ValueError("Timestamp must be timezone-aware")

    year_start = pd.Timestamp(timestamp.year, 1, 1, tz=timestamp.tzinfo)
    year_end = pd.Timestamp(timestamp.year + 1, 1, 1, tz=timestamp.tzinfo)
    total_seconds = (year_end - year_start).total_seconds()
    elapsed_seconds = (timestamp - year_start).total_seconds()
    return elapsed_seconds / total_seconds

def add_year_progress(df):
    df['year_progress'] = df.index.map(year_progress)

def read_data():
# Get all CSV files in the directory
    all_files = glob.glob(os.path.join(path, "[12]*.csv"))
    all_files.sort()

# List to store individual DataFrames
    df_list = []

# Read each CSV file and process it
    for filename in all_files:
        df = pd.read_csv(filename, index_col=2, header=0, names=["entity", "power", "date"], dtype = {'power': np.float32 }, na_values=["unavailable"])
        
        entity = df['entity'].iloc[0]
        entity = entity.replace("sensor.", "")
        df = df.drop('entity', axis=1)

        df = df.rename(columns={'power': entity})

        df.index = pd.to_datetime(df.index)

        df_list.append(df)

    # Concatenate all DataFrames in the list
    combined_df = pd.concat(df_list, axis=1)
    combined_df = combined_df.sort_index()
    # Remove any duplicate indices, keeping the last occurrence
    # XXX not sur this is needed
    combined_df = combined_df[~combined_df.index.duplicated(keep='last')]

    # Resample to 10min intervals to avoid sub-second "precision" BS
    df = combined_df
    df = df.resample('10min').mean().dropna(how="all")

    # Drop lines where total power is too low
   # df=df[df['hm1500_powerdc'] > 40]

    df = calculate_ratios(df)
    add_sun_positions(df)
    add_year_progress(df)
    return df

