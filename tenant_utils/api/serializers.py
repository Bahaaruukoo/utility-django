from rest_framework import serializers

from bills.models import MeterReading


class MeterReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model = MeterReading
        fields = [
            "id",
            "meter",
            "reading_value",
            "reading_date",
            "previous_reading",
            "consumption",
            "reading_status",
        ]
        read_only_fields = [
            "previous_reading",
            "consumption",
            "reading_status",
            "reading_date"
        ]

    def create(self, validated_data):
        request = self.context["request"]

        validated_data["reader"] = request.user
        validated_data["branch"] = request.user.branch

        reading = MeterReading.objects.create(**validated_data)

        return reading