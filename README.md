# Traitorous Models: Benchmarking Open Source Models in 'The Traitors'
 
This project simulates the reality TV show game "[The Traitors](https://en.wikipedia.org/wiki/The_Traitors_(franchise))" pitting various AI models against each other.


## Some Exciting Playbacks

The simulation utilizes [plomp](https://github.com/michaelgiba/plomp) for visualizing the game state and tracking the context provided to the models throughout the game.
Some example visualizations of what happened in the game:

### Example #1: Faithfuls Turn on Each Other After Eliminating the Sole Traitor in First Round Table

[Plomp Visualization Link (xt10xy7k)](https://michaelgiba.github.io/the-traitors/results/traitors/xt10xy7k/plomp.html)

> Fletcher(faithful, qwen-2.5-32b) said: "I'm voting to eliminate Taylor(faithful, gemma2-9b-it). Taylor(faithful, gemma2-9b-it) has been very aggressive in their accusations and seems to be leading the charge to eliminate others. Their behavior just seems too pushy and manipulative, which doesn't sit right with me. I think we should vote out Taylor(faithful, gemma2-9b-it) to ensure we're not leaving any false leads."



## Open Source Models Used

All of the game simulations ran for free using local inference and public free models from Groq.

### Local Models

*   microsoft_Phi-4-mini-instruct-IQ4_XS.gguf

### Groq Models

* deepseek-r1-distill-llama-70b
* deepseek-r1-distill-qwen-32b
* gemma2-9b-it
* llama-3.1-8b-instant
* meta-llama/llama-4-maverick-17b
* meta-llama/llama-4-scout-17b
* qwen-2.5-32b
* qwen-qwq-32b

## Analysis Results

Here are some summary statistics from simulations. 

**Average Earnings per Game**
![Average Earnings per Game by Model](./analysis/traitors/average_earnings_per_game.png)

**Win Rates by Model:**
![Win Rates by Model](./analysis/traitors/win_rates_by_model.png)

**Model Ratings (Elo-like):**
![Model Ratings](./analysis/traitors/model_rating_elo.png)

**Most Effective Traitors (Win Rate as Traitor):**
![Effective Traitors](./analysis/traitors/effective_traitors_ranking.png)

**Most Successful Faithfuls (Win Rate as Faithful):**
![Successful Faithfuls](./analysis/traitors/successful_faithfuls_ranking.png)


## Acknowledgements

Took inspiration from https://github.com/lechmazur/elimination_game