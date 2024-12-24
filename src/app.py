from flask import Flask, render_template, request, jsonify
from pulp import *
import pandas as pd
import webbrowser
from threading import Timer


# Initialize Flask app
app = Flask(__name__)

# Load the food database
FOODS = pd.read_csv('food_test.csv')


@app.route('/')
def home():
    """Render the homepage with the input form."""
    return render_template('index.html')

@app.route('/about.html')
def about():
    return render_template('about.html')

def open_browser():
    """Open the default web browser after Flask server starts."""
    webbrowser.open_new("http://127.0.0.1:5000")

@app.route('/generate', methods=['POST'])
def generate_meal_plan():
    """Handle meal plan generation based on user inputs."""
    try:
        # Get inputs from the form
        min_fat = float(request.form['min_fat'])
        min_protein = float(request.form['min_protein'])
        min_carbs = float(request.form['min_carbs'])
        diet_type = request.form['diet_type']

        # Retrieve allergy checkboxes
        allergies = {
            "Milk": request.form.get('milk') == 'on',
            "Eggs": request.form.get('eggs') == 'on',
            "Gluten": request.form.get('gluten') == 'on',
            "Fish": request.form.get('fish') == 'on',
            "Meat": request.form.get('meat') == 'on',
            "Nuts": request.form.get('nuts') == 'on'
        }

        # Filter foods based on dietary preferences
        foods = FOODS.copy()
        if diet_type == 'vegan':
            foods = foods[foods['vegan'] == True]
        elif diet_type == 'vegetarian':
            foods = foods[foods['vegetarian'] == True]
        elif diet_type == 'low carb':
            foods = foods[foods['carbs'] <= 10]
        elif diet_type == 'high carb':
            foods = foods[foods['carbs'] >= 30]

        # Filter out foods based on allergies
        for allergy, has_allergy in allergies.items():
            if has_allergy:
                foods = foods[foods[f"contains_{allergy.lower()}"] == False]

        # Create the LP problem
        prob = LpProblem("Meal Planning", LpMinimize)
        food_vars = LpVariable.dicts("Food", foods.index, lowBound=0, cat='Continuous')

        # Objective: Minimize the total price
        prob += lpSum([food_vars[i] * foods.loc[i, 'price'] for i in foods.index])

        # Nutritional constraints
        prob += lpSum([food_vars[i] * foods.loc[i, 'fat'] for i in foods.index]) >= min_fat
        prob += lpSum([food_vars[i] * foods.loc[i, 'protein'] for i in foods.index]) >= min_protein
        prob += lpSum([food_vars[i] * foods.loc[i, 'carbs'] for i in foods.index]) >= min_carbs

        # Add a maximum servings constraint
        max_servings = 3
        for i in foods.index:
            prob += food_vars[i] <= max_servings
        # Solve the problem
        prob.solve()

        # Generate results
        results = []
        total_cost = 0
        for i in foods.index:
            if food_vars[i].varValue > 0:
                results.append({
                    'name': foods.loc[i, 'name'],
                    'servings': food_vars[i].varValue,
                    'price': foods.loc[i, 'price']
                })
                total_cost += food_vars[i].varValue * foods.loc[i, 'price']

        # Render the results in HTML
        return render_template('results.html', results=results, total_cost=total_cost)

    except Exception as e:
        # Handle errors and show them in the UI
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    # Only open the browser if running in the main process
    import os
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()
    app.run(debug=True)