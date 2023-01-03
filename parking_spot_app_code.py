from shiny import *
from shiny.types import FileInfo
import networkx as nx
import numpy as np
import matplotlib.pyplot as plt
import copy
import pandas as pd
import asyncio
import io
from datetime import date
from pathlib import Path

app_ui = ui.page_fluid(
    ui.panel_title('Parking Spot Re-Allocator'),
    ui.layout_sidebar(
        ui.panel_sidebar(
            ui.input_numeric('pref_count', 'How many parking spots are to be assigned?', value=15),
            ui.input_file('pref_input', 'Upload a CSV', accept=['.csv'], multiple=False), 
            ui.input_checkbox('efficiency_gain_viewer', 'Observe Efficiency Gains'), 
            ui.download_button("download", "Generate Sample Data"), 
            ui.input_select("data_type", "Select Data Type", ['Random', 'Endogenous']),
        ), 
        ui.panel_main(
            ui.output_table('final_allocation'), 
            ui.output_table('initial_preferences')
        ),
    ),
)

def sample_ttc_data(units=15, exog=True):
    apts = list(range(1700, 1700+units))
    if exog:
        data={apts[i]:[i+1, list(np.random.choice(np.arange(1, units+1), units, replace=False))] for i in range(units)}
    else:
        data = {}
        p1, p2, p3, others = .5, .2, .1, .2/(units-3)
        for i in range(len(apts)):
            p = []
            for j in range(len(apts)):
                if j==i:
                    p.append(p1)
                elif abs(i - j)==1:
                    p.append(p2)
                elif abs(i-j)==2:
                    p.append(p3)
                else:
                    p.append(others)
            p = np.array(p)/sum(p)
            data[apts[i]] = [i+1, list(np.random.choice(np.arange(1, units+1), units, replace=False, p=p))]
        
    return data

def to_pref_dic(df):
    keys = [unit for unit in df['Unit']]
    values = []
    for i in range(len(df)):
        current_assignment = df.iloc[i, 1]
        ordered_prefs = []
        for ordered_pref in df.iloc[i, 2:]:
            ordered_prefs.append(ordered_pref)
        values.append([current_assignment, list(ordered_prefs)])
    pref_dic = {keys[i]:values[i] for i in range(len(df))}
    return pref_dic

def parking_ttc(dic):
    #lists to populate
    matches = []
    matched = []
    assigned = []
    #sub-function definitions
    #a function that takes in the latest preferences dictionary and returns edges for a directed graph
    def edges(dic):
        top_prefs = []
        for apt in dic: #for each apt, find what apartment has their top pref as its current assignment 
            best = dic[apt][1][0]
            for other in dic:
                if dic[other][0]==best:
                    match=other
                    top_prefs.append((apt, match))
                else:
                    pass
        return(top_prefs) #return a list of tuples (i, j), where j has i's most preferred assignment
    def cycles(dic):
        #create a graph object from which to identify a list of cycles or lack thereof
        G = nx.DiGraph() 
        G.add_edges_from(edges(dic))
        cycles = list(nx.simple_cycles(G))
        for cycle in cycles:
            first = cycle[0]
            for apt in cycle:
                #if the apartment is the last in the cycle, they get the first's spot
                if cycle.index(apt)==(len(cycle)-1):
                    matches.append((apt, first))
                    matched.append(apt)
                    assigned.append(dic[first][0])
                else: #otherwise, people just get whose after them
                    next_apt = cycle[cycle.index(apt)+1]
                    matches.append((apt, next_apt))
                    matched.append(apt)
                    assigned.append(dic[next_apt][0])
        dic = {key:value for (key, value) in dic.items() if ((key not in matched)|(value[0] not in assigned))}
        for apt in dic: #update each apartment's preference list to remove any spots that were just assigned
            dic[apt][1] = [pref for pref in dic[apt][1] if pref not in assigned]
        return(dic) #return the latest dic
    
    while len(dic)>0:
        dic = cycles(dic)
    apts = []
    assignments = []
    for i, j in zip(matched, assigned):
        apts.append(i)
        assignments.append(j)
        final_aloc = pd.DataFrame({assignment: apt for assignment, apt in zip(apts, assignments)}, index=['Allocation'])
    return final_aloc

def server(input, output, session):
    @output
    @render.table
    def initial_preferences():
        file_infos = input.pref_input()
        if file_infos is not None:
            initial_prefs = pd.read_csv(file_infos[0]['datapath']).iloc[:, :2+input.pref_count()]
            final = parking_ttc(to_pref_dic(initial_prefs))
            if not input.efficiency_gain_viewer():
                return (
                    initial_prefs.style.set_table_attributes(
                        'class="dataframe shiny-table table w-auto"'
                    )
                    .hide(axis='index')
                    .set_table_styles([dict(selector='tr', props=[('text-align', 'center')])])
                )
            else:
                return (
                    initial_prefs.style.set_table_attributes(
                        'class="dataframe shiny-table table w-auto"'
                    )
                    .hide(axis='index')
                    .set_table_styles([dict(selector='tr', props=[('text-align', 'center')])])
                    .data
                    .style.apply(lambda x: ["background: orange" if i>0 and v == x.iloc[1] else 
                                            "background: green" if i>0 and v == final[x[0]].values else
                                            "" for i, v in enumerate(x)], axis=1)
                )

    @output
    @render.table
    def final_allocation():
        file_infos = input.pref_input()
        if file_infos is not None:
            initial_prefs = pd.read_csv(file_infos[0]['datapath'])
            final = parking_ttc(to_pref_dic(initial_prefs))
            final = final.loc[:, list(range(np.min(final.columns), np.max(final.columns)+1))]
            return (
                final.style.set_table_attributes(
                    'class="dataframe shiny-table table w-auto"'  
                )
                .set_table_styles([dict(selector='tr', props=[('text-align', 'center')])])
            )

    
    @session.download(
        filename=lambda: f"data-{date.today().isoformat()}-{np.random.randint(100,999)}.csv"
    )
    async def download():
        await asyncio.sleep(0.25)
        if input.data_type()=='Random':
            some_data = sample_ttc_data(units=15, exog=True)
        else:
            some_data = sample_ttc_data(units=15, exog=False)
        yield "Unit,Current Spot,Pref 1,Pref 2,Pref 3,Pref 4,Pref 5,Pref 6,Pref 7,Pref 8,Pref 9,Pref 10,Pref 11,Pref 12,Pref 13,Pref 14,Pref 15\n"
        for unit in list(some_data.keys()):
            prefs = ','.join(map(str, some_data[unit][1]))
            row = str(unit)+','+str(some_data[unit][0])+','+prefs+'\n'
            yield row
            
        
app = App(app_ui, server)