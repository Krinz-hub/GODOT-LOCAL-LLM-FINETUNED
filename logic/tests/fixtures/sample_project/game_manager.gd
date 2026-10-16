extends Node
class_name GameManager

signal score_updated(score: int)

var score: int = 0

func _ready() -> void:
	print("GameManager initialized")

func add_score(points: int) -> void:
	score += points
	score_updated.emit(score)
