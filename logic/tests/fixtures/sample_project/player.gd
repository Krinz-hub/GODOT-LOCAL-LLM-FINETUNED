extends CharacterBody2D
class_name Player

signal health_changed(new_health: int)
signal died

@export var speed: float = 300.0
@export var jump_velocity: float = -400.0

var health: int = 100

func _physics_process(delta: float) -> void:
	velocity += get_gravity() * delta
	move_and_slide()

func take_damage(amount: int) -> void:
	health = max(0, health - amount)
	health_changed.emit(health)
	if health == 0:
		died.emit()
