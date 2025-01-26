from flask import Flask, render_template, request, jsonify
from pulp import *
import pandas as pd
import os
import webbrowser
from threading import Timer

# Initialize Flask app
app = Flask(__name__)

# Nutrient calculator logic
def calculate_nutrient_needs(weight_kg, height_cm, age, sex, activity_level):
    # Calculate Basal Energy Expenditure (BEE) using Harris-Benedict Equation
    if sex == 'male':
        bee = 66.5 + (13.8 * weight_kg) + (5.0 * height_cm) - (6.8 * age)
    elif sex == 'female':
        bee = 655.1 + (9.6 * weight_kg) + (1.9 * height_cm) - (4.7 * age)
    else:
        return None

    # Adjust BEE for activity level
    total_calories = bee * activity_level

    # Protein needs (0.8 to 1.0 g per kg of body weight)
    protein_min = 0.8 * weight_kg
    protein_max = 1.0 * weight_kg

    # Fat needs (30% of total daily calories)
    fat_calories = 0.30 * total_calories
    fat_grams = fat_calories / 9  # 1 gram of fat = 9 calories

    # Carbohydrate needs (45% to 65% of total daily calories)
    carb_min_calories = 0.45 * total_calories
    carb_max_calories = 0.65 * total_calories
    carb_min_grams = carb_min_calories / 4  # 1 gram of carbohydrate = 4 calories
    carb_max_grams = carb_max_calories / 4

    return {
        'total_calories': total_calories,
        'fat_g': fat_grams,
        'protein_min_g': protein_min,
        'protein_max_g': protein_max,
        'carb_min_g': carb_min_grams,
        'carb_max_g': carb_max_grams
    }

# Route for the nutrient calculator
@app.route('/calculator', methods=['GET', 'POST'])
def calculator():
    result = None
    if request.method == 'POST':
        try:
            weight_kg = float(request.form['weight_kg'])
            height_cm = float(request.form['height_cm'])
            age = int(request.form['age'])
            sex = request.form['sex']
            activity_level = float(request.form['activity_level'])

            if weight_kg > 0 and height_cm > 0 and age > 0 and activity_level > 0:
                result = calculate_nutrient_needs(weight_kg, height_cm, age, sex, activity_level)
            else:
                result = "Please enter valid values greater than zero."
        except ValueError:
            result = "Invalid input. Please ensure all fields are filled correctly."
    return render_template('calculator.html', result=result)

# Load the food database
FOODS = pd.read_csv('food_test.csv')

@app.route('/')
def home():
    """Render the homepage with the input form."""
    # Pass the list of foods to populate the dropdown options
    food_names = FOODS['name'].tolist()
    return render_template('index.html', food_names=food_names)

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

        # Retrieve scroll-down selections for including and excluding foods
        include_foods = request.form.getlist('include_foods')
        exclude_foods = request.form.getlist('exclude_foods')

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

        # Exclude foods from the exclude_foods list
        if exclude_foods:
            foods = foods[~foods['name'].isin(exclude_foods)]

        # Ensure foods are available for optimization
        if foods.empty:
            return "No foods available based on your selections. Please adjust your preferences."

        # Create the LP problem
        prob = LpProblem("Meal Planning", LpMinimize)
        food_vars = LpVariable.dicts("Food", foods.index, lowBound=0, cat='Continuous')

        # Force inclusion of foods in the include_foods list
        if include_foods:
            included_indices = foods[foods['name'].isin(include_foods)].index
            for idx in included_indices:
                prob += food_vars[idx] >= 1  # Ensure at least 1 serving of each included food

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

        # Generate results and calculate totals
        results = []
        total_cost = 0
        total_fats = 0
        total_carbs = 0
        total_proteins = 0

        for i in foods.index:
            if food_vars[i].varValue > 0:
                servings = food_vars[i].varValue
                results.append({
                    'name': foods.loc[i, 'name'],
                    'servings': servings,
                    'price': foods.loc[i, 'price']
                })
                total_cost += servings * foods.loc[i, 'price']
                total_fats += servings * foods.loc[i, 'fat']
                total_carbs += servings * foods.loc[i, 'carbs']
                total_proteins += servings * foods.loc[i, 'protein']

        # Render the results in HTML
        return render_template(
            'results.html',
            results=results,
            total_cost=round(total_cost, 2),
            total_fats=round(total_fats, 2),
            total_carbs=round(total_carbs, 2),
            total_proteins=round(total_proteins, 2)
        )

    except Exception as e:
        # Handle errors and show them in the UI
        return jsonify({'error': str(e)}), 400

if __name__ == '__main__':
    # Only open the browser if running in the main process
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()
    app.run(debug=True)
